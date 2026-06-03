import os
import re
import subprocess
from pathlib import Path


class PhddnsWatchdogService:
    label = "com.fit.phddns-watchdog"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    log_path = Path("/tmp/fit-phddns-watchdog.log")

    def status(self) -> dict:
        installed = self.plist_path.exists()
        launchctl = self._launchctl_list()
        enabled = installed and launchctl.returncode == 0
        output = launchctl.stdout if launchctl.returncode == 0 else ""
        pid = self._parse_int_field(output, "PID")
        return {
            "installed": installed,
            "enabled": enabled,
            "running": pid is not None,
            "pid": pid,
            "last_exit_status": self._parse_int_field(output, "LastExitStatus"),
            "label": self.label,
            "plist_path": str(self.plist_path),
            "log_lines": self._read_log_tail(),
            "message": "" if installed else "花生壳监控服务尚未安装",
        }

    def set_enabled(self, enabled: bool) -> dict:
        if not self.plist_path.exists():
            raise RuntimeError("花生壳监控服务尚未安装，请先运行 launchd 安装脚本")
        if enabled:
            self._enable()
        else:
            self._disable()
        item = self.status()
        item["message"] = "花生壳监控服务已开启" if enabled else "花生壳监控服务已关闭"
        return item

    def _enable(self) -> None:
        current = self._launchctl_list()
        if current.returncode != 0:
            bootstrap = self._run_launchctl(["bootstrap", self._domain(), str(self.plist_path)])
            if bootstrap.returncode != 0 and "already bootstrapped" not in bootstrap.stderr:
                legacy = self._run_launchctl(["load", str(self.plist_path)])
                if legacy.returncode != 0:
                    raise RuntimeError(self._command_error("开启花生壳监控服务失败", bootstrap, legacy))
        kickstart = self._run_launchctl(["kickstart", "-k", f"{self._domain()}/{self.label}"])
        if kickstart.returncode != 0:
            legacy = self._run_launchctl(["start", self.label])
            if legacy.returncode != 0:
                raise RuntimeError(self._command_error("启动花生壳监控服务失败", kickstart, legacy))

    def _disable(self) -> None:
        current = self._launchctl_list()
        if current.returncode != 0:
            return
        bootout = self._run_launchctl(["bootout", self._domain(), str(self.plist_path)])
        if bootout.returncode != 0:
            legacy = self._run_launchctl(["unload", str(self.plist_path)])
            if legacy.returncode != 0:
                raise RuntimeError(self._command_error("关闭花生壳监控服务失败", bootout, legacy))

    def _launchctl_list(self) -> subprocess.CompletedProcess[str]:
        return self._run_launchctl(["list", self.label])

    def _run_launchctl(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/launchctl", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def _domain(self) -> str:
        return f"gui/{os.getuid()}"

    def _read_log_tail(self, limit: int = 6) -> list[str]:
        if not self.log_path.exists():
            return []
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        except OSError:
            return []

    @staticmethod
    def _parse_int_field(output: str, field: str) -> int | None:
        match = re.search(rf'"?{re.escape(field)}"?\s*=\s*(-?\d+)', output)
        if not match:
            return None
        return int(match.group(1))

    @staticmethod
    def _command_error(prefix: str, *results: subprocess.CompletedProcess[str]) -> str:
        details = []
        for result in results:
            text = (result.stderr or result.stdout or "").strip()
            if text:
                details.append(text)
        return f"{prefix}：{'；'.join(details) if details else 'launchctl 未返回错误详情'}"
