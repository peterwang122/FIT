from datetime import date

import httpx
from celery import Task

from app.core.config import settings
from app.core.redis_client import redis_client
from app.workers.celery_app import celery_app


def _collector_lock_key(ts_code: str, start_date: str | None, end_date: str | None) -> str:
    return f"collector:lock:{ts_code}:{start_date or '-'}:{end_date or '-'}"


def _stock_temp_lock_key(stock_code: str, start_date: str | None, end_date: str | None) -> str:
    return f"stock-temp:lock:{stock_code}:{start_date or '-'}:{end_date or '-'}"


@celery_app.task(
    bind=True,
    name="tasks.collect_stock_data",
    autoretry_for=(httpx.HTTPError, TimeoutError),
    retry_backoff=settings.collector_task_retry_backoff_seconds,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.collector_task_max_retries},
    soft_time_limit=settings.collector_task_soft_time_limit_seconds,
    time_limit=settings.collector_task_time_limit_seconds,
)
def collect_stock_data(
    self: Task,
    ts_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
):
    """向外部数据采集服务发送采集请求，支持重试/超时/去重幂等锁。"""
    lock_key = _collector_lock_key(ts_code=ts_code, start_date=start_date, end_date=end_date)
    # setnx + ex：相同采集窗口在短时间内只允许一个任务对上游发起请求。
    lock_acquired = redis_client.set(lock_key, self.request.id, nx=True, ex=settings.collector_dedupe_lock_ttl_seconds)
    if not lock_acquired:
        return {
            "requested_at": date.today().isoformat(),
            "status": "deduplicated",
            "message": "same payload is already being collected",
        }

    payload = {
        "ts_code": ts_code,
        "start_date": start_date,
        "end_date": end_date,
    }

    try:
        with httpx.Client(base_url=settings.collector_base_url, timeout=settings.collector_timeout_seconds) as client:
            response = client.post("/collect/stock-data", json=payload)
            response.raise_for_status()
            return {
                "requested_at": date.today().isoformat(),
                "status": "ok",
                "upstream_response": response.json(),
            }
    finally:
        owner = redis_client.get(lock_key)
        if owner == self.request.id:
            redis_client.delete(lock_key)


@celery_app.task(
    bind=True,
    name="tasks.collect_stock_qfq_data",
    autoretry_for=(httpx.HTTPError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.stock_temp_task_max_retries},
    soft_time_limit=settings.stock_temp_task_soft_time_limit_seconds,
    time_limit=settings.stock_temp_task_time_limit_seconds,
)
def collect_stock_qfq_data(
    self: Task,
    stock_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
):
    lock_key = _stock_temp_lock_key(stock_code=stock_code, start_date=start_date, end_date=end_date)
    lock_acquired = redis_client.set(lock_key, self.request.id, nx=True, ex=settings.collector_dedupe_lock_ttl_seconds)
    if not lock_acquired:
        return {
            "requested_at": date.today().isoformat(),
            "status": "deduplicated",
            "message": "same payload is already being collected",
        }

    payload = {
        "stock_code": stock_code,
        "start_date": start_date,
        "end_date": end_date,
    }

    try:
        with httpx.Client(
            base_url=settings.stock_temp_service_base_url,
            timeout=settings.stock_temp_service_timeout_seconds,
        ) as client:
            response = client.post("/collect", json=payload)
            response.raise_for_status()
            response_json = response.json()
            upstream_status = str(response_json.get("status", "")).upper()
            if upstream_status not in {"SUCCESS", "UNCHANGED"}:
                raise RuntimeError(f"unexpected stock temp service status: {upstream_status or 'UNKNOWN'}")
            return {
                "requested_at": date.today().isoformat(),
                "status": "ok",
                "upstream_status": upstream_status,
                "upstream_response": response_json,
            }
    finally:
        owner = redis_client.get(lock_key)
        if owner == self.request.id:
            redis_client.delete(lock_key)
