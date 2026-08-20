import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend"
PYTHON = Path(sys.executable)


def run(args: list[str], cwd: Path = REPO_ROOT) -> int:
    return subprocess.run(args, cwd=cwd, check=False).returncode


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _is_lan_test() -> bool:
    return os.environ.get("APP_ENV", "").strip().lower() == "lan-test"


def _backend_lan_test_issues() -> list[str]:
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.lan_test import lan_test_contract_issues

    return lan_test_contract_issues()


def _backend_redact_database_url(url: str) -> str:
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.lan_test import redact_database_url

    return redact_database_url(url)


def _load_lan_test_env() -> None:
    _load_env_file(REPO_ROOT / ".env.lan-test")
    _load_env_file(BACKEND_ROOT / ".env.lan-test")


def _doctor() -> int:
    _load_lan_test_env()
    if not _is_lan_test():
        print("[FAIL] APP_ENV should be 'lan-test'")
        return 1
    issues = _backend_lan_test_issues()
    print(f"APP_ENV={os.environ.get('APP_ENV', '')}")
    print(f"DATABASE_URL={_backend_redact_database_url(os.environ.get('DATABASE_URL', ''))}")
    print(f"REDIS_URL={os.environ.get('REDIS_URL', '')}")
    print(f"COLLECTION_EXECUTION_MODE={os.environ.get('COLLECTION_EXECUTION_MODE', '')}")
    print(f"COLLECTION_ALLOWED_KEYS={os.environ.get('COLLECTION_ALLOWED_KEYS', '')}")
    if issues:
        for issue in issues:
            print(f"[FAIL] {issue}")
        return 1
    print("[OK] lan-test 配置契约完整")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-platform FIT service helper.")
    parser.add_argument(
        "command",
        choices=[
            "infra",
            "api",
            "worker",
            "beat",
            "lan-test-api",
            "lan-test-worker",
            "doctor",
            "frontend",
            "frontend-build",
            "backend-check",
        ],
    )
    args = parser.parse_args()

    if args.command == "infra":
        return run(["docker", "compose", "up", "-d"])
    if args.command == "api":
        return run([str(PYTHON), "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"], BACKEND_ROOT)
    if args.command == "worker":
        return run([str(PYTHON), "-m", "celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info"], BACKEND_ROOT)
    if args.command == "beat":
        if _is_lan_test():
            print("lan-test 环境禁止启动 Celery Beat", file=sys.stderr)
            return 2
        return run([str(PYTHON), "-m", "celery", "-A", "app.workers.celery_app", "beat", "--loglevel=info"], BACKEND_ROOT)
    if args.command == "lan-test-api":
        _load_lan_test_env()
        issues = _backend_lan_test_issues()
        if issues:
            for issue in issues:
                print(f"[FAIL] {issue}", file=sys.stderr)
            return 1
        return run(
            [str(PYTHON), "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"],
            BACKEND_ROOT,
        )
    if args.command == "lan-test-worker":
        _load_lan_test_env()
        issues = _backend_lan_test_issues()
        if issues:
            for issue in issues:
                print(f"[FAIL] {issue}", file=sys.stderr)
            return 1
        return run(
            [
                str(PYTHON),
                "-m",
                "celery",
                "-A",
                "app.workers.celery_app",
                "worker",
                "--loglevel=info",
            ],
            BACKEND_ROOT,
        )
    if args.command == "doctor":
        return _doctor()
    if args.command == "frontend":
        return run(["npm", "run", "dev"], FRONTEND_ROOT)
    if args.command == "frontend-build":
        return run(["npm", "run", "build"], FRONTEND_ROOT)
    if args.command == "backend-check":
        return run([str(PYTHON), "-m", "compileall", "-q", "app"], BACKEND_ROOT)

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
