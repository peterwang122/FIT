import argparse
import plistlib
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend"
PYTHON = Path(sys.executable)
CONDA = Path("/Users/wanghequan/miniconda3/bin/conda")
NODE = Path("/Users/wanghequan/miniconda3/envs/FIT/bin/node")
NPM = Path("/Users/wanghequan/miniconda3/envs/FIT/bin/npm")
NPM_CLI = Path("/Users/wanghequan/miniconda3/envs/FIT/lib/node_modules/npm/bin/npm-cli.js")
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"


SERVICES = {
    "api": {
        "label": "com.fit.api",
        "args": [str(PYTHON), "-m", "uvicorn", "app.main:app", "--port", "8000"],
        "cwd": BACKEND_ROOT,
    },
    "worker": {
        "label": "com.fit.worker",
        "args": [str(PYTHON), "-m", "celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info"],
        "cwd": BACKEND_ROOT,
    },
    "beat": {
        "label": "com.fit.beat",
        "args": [str(PYTHON), "-m", "celery", "-A", "app.workers.celery_app", "beat", "--loglevel=info"],
        "cwd": BACKEND_ROOT,
    },
    "frontend": {
        "label": "com.fit.frontend",
        "args": [str(NODE), str(NPM_CLI), "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"],
        "cwd": FRONTEND_ROOT,
    },
}


def plist_payload(name: str, service: dict) -> dict:
    log_dir = REPO_ROOT / "runtime" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return {
        "Label": service["label"],
        "ProgramArguments": service["args"],
        "WorkingDirectory": str(service["cwd"]),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log_dir / f"{name}.out.log"),
        "StandardErrorPath": str(log_dir / f"{name}.err.log"),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
            "PATH": "/Users/wanghequan/miniconda3/envs/FIT/bin:/Users/wanghequan/miniconda3/bin:"
            "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        },
    }


def install(service_name: str) -> Path:
    service = SERVICES[service_name]
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    plist_path = LAUNCH_AGENTS / f"{service['label']}.plist"
    with plist_path.open("wb") as file:
        plistlib.dump(plist_payload(service_name, service), file)
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    return plist_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Install macOS launchd services for FIT.")
    parser.add_argument("services", nargs="*", choices=sorted(SERVICES), default=sorted(SERVICES))
    args = parser.parse_args()
    for service_name in args.services:
        plist_path = install(service_name)
        print(f"installed {service_name}: {plist_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
