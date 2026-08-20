"""局域网测试环境（lan-test）统一运行时契约校验。

API（uvicorn / FastAPI 启动）、Celery worker、任务执行入口和采集白名单
共用本模块：只要 ``APP_ENV=lan-test``，任何安全开关不符合契约都必须在
访问数据库、Redis 或外部网络之前拒绝（fail-closed）。
"""

from sqlalchemy.engine import make_url

from app.core.config import settings


LAN_TEST_DB_NAME = "stock_info_test"

LAN_TEST_CONTRACT = {
    "app_env": "lan-test",
    "startup_schema_mode": "app-only",
    "bootstrap_default_tasks": False,
    "scheduled_tasks_enabled": False,
    "outbound_notifications_enabled": False,
    "collection_execution_mode": "allowlist",
    "codex_reset_watchdog_enabled": False,
}


def lan_test_contract_issues() -> list[str]:
    """非 lan-test 环境返回空列表；lan-test 环境返回所有契约违规项。"""
    if str(settings.app_env or "").strip().lower() != "lan-test":
        return []

    issues: list[str] = []
    for key, expected in LAN_TEST_CONTRACT.items():
        actual = getattr(settings, key)
        if isinstance(expected, str):
            if str(actual or "").strip().lower() != expected:
                issues.append(f"{key} should be {expected!r}, got {actual!r}")
        elif bool(actual) is not expected:
            issues.append(f"{key} should be {expected!r}, got {actual!r}")

    try:
        db_name = make_url(settings.database_url).database
    except Exception as exc:  # pragma: no cover - defensive
        db_name = None
        issues.append(f"database_url is not a valid SQLAlchemy URL: {exc}")
    if db_name != LAN_TEST_DB_NAME:
        issues.append(f"database must be exactly {LAN_TEST_DB_NAME}, got {db_name!r}")
    return issues


def ensure_lan_test_runtime_safe() -> None:
    issues = lan_test_contract_issues()
    if issues:
        raise RuntimeError("lan-test contract violation: " + "; ".join(issues))


def redact_database_url(url: str) -> str:
    """脱敏数据库 URL：隐藏用户名后的密码，错误信息不回显密钥。"""
    try:
        parsed = make_url(str(url or ""))
    except Exception:
        return "<invalid-database-url>"
    if not parsed.password:
        return str(url or "")
    return str(parsed.set(password="***"))
