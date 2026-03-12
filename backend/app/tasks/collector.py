from datetime import date

import httpx

from app.core.config import settings
from app.workers.celery_app import celery_app


@celery_app.task(name="tasks.collect_stock_data")
def collect_stock_data(ts_code: str, start_date: str | None = None, end_date: str | None = None):
    """向外部数据采集服务发送采集请求。"""
    payload = {
        "ts_code": ts_code,
        "start_date": start_date,
        "end_date": end_date,
    }
    with httpx.Client(base_url=settings.collector_base_url, timeout=settings.collector_timeout_seconds) as client:
        response = client.post("/collect/stock-data", json=payload)
        response.raise_for_status()
        return {
            "requested_at": date.today().isoformat(),
            "upstream_response": response.json(),
        }
