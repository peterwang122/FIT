#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal  # noqa: E402
from app.services.wechat_miniapp_sync_service import WechatMiniappSyncService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="同步 FIT 展示数据到微信云开发")
    parser.add_argument("--full", action="store_true", help="同步全部历史；默认仅同步最近配置天数")
    parser.add_argument(
        "--with-notification",
        action="store_true",
        help="同时处理最新通知事件；仅用于明确的人工恢复，默认只同步看板数据",
    )
    parser.add_argument("--dry-run", action="store_true", help="只生成数据并输出数量，不发起网络请求")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with SessionLocal() as db:
        service = WechatMiniappSyncService(db)
        if args.dry_run:
            start_date = service._start_date(args.full)
            result = {
                "status": "dry_run",
                "full": args.full,
                "table_count": len(service.build_table_records(start_date)),
                "series_count": len(service.build_series_records(start_date)),
                "score_count": len(service.build_score_records(start_date)),
                "has_notification_event": bool(
                    args.with_notification and service.build_notification_event()
                ),
            }
        else:
            result = service.sync(
                full=args.full,
                include_notification=args.with_notification,
            )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("status") in {"success", "disabled", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
