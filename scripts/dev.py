import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend"
PYTHON = Path(sys.executable)


def run(args: list[str], cwd: Path = REPO_ROOT) -> int:
    return subprocess.run(args, cwd=cwd, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-platform FIT service helper.")
    parser.add_argument(
        "command",
        choices=[
            "infra",
            "api",
            "worker",
            "beat",
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
        return run([str(PYTHON), "-m", "celery", "-A", "app.workers.celery_app", "beat", "--loglevel=info"], BACKEND_ROOT)
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
