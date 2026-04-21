import time
from datetime import date
from uuid import uuid4

import httpx
from celery import Task

from app.core.config import settings
from app.core.redis_client import redis_client
from app.workers.celery_app import celery_app


def _collector_lock_key(ts_code: str, start_date: str | None, end_date: str | None) -> str:
    return f"collector:lock:{ts_code}:{start_date or '-'}:{end_date or '-'}"


def _stock_temp_lock_key(stock_code: str, start_date: str | None, end_date: str | None) -> str:
    return f"stock-temp:lock:{stock_code}:{start_date or '-'}:{end_date or '-'}"


def _index_temp_lock_key(market: str) -> str:
    return f"index-temp:lock:{market}"


def _daily_temp_lock_key(collector_key: str) -> str:
    return f"daily-temp:lock:{collector_key}"


def _forex_temp_lock_key(symbol_code: str) -> str:
    return f"forex-temp:lock:{symbol_code}"


def _raise_with_response_detail(response: httpx.Response) -> None:
    body_text = ""
    try:
        body_text = response.text.strip()
    except Exception:
        body_text = ""
    detail = f"upstream returned {response.status_code}"
    if body_text:
        detail += f", body={body_text[:1000]}"
    raise httpx.HTTPStatusError(detail, request=response.request, response=response)


def run_stock_data_collection_request(
    ts_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    request_id: str | None = None,
):
    lock_key = _collector_lock_key(ts_code=ts_code, start_date=start_date, end_date=end_date)
    owner_token = request_id or f"manual:{uuid4()}"
    lock_acquired = redis_client.set(lock_key, owner_token, nx=True, ex=settings.collector_dedupe_lock_ttl_seconds)
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
        with httpx.Client(
            base_url=settings.collector_base_url,
            timeout=settings.collector_timeout_seconds,
            trust_env=False,
        ) as client:
            response = client.post("/collect/stock-data", json=payload)
            response.raise_for_status()
            return {
                "requested_at": date.today().isoformat(),
                "status": "ok",
                "upstream_response": response.json(),
            }
    finally:
        owner = redis_client.get(lock_key)
        if owner == owner_token:
            redis_client.delete(lock_key)


def run_stock_hfq_collection_request(
    stock_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    request_id: str | None = None,
):
    lock_key = _stock_temp_lock_key(stock_code=stock_code, start_date=start_date, end_date=end_date)
    owner_token = request_id or f"manual:{uuid4()}"
    lock_acquired = redis_client.set(lock_key, owner_token, nx=True, ex=settings.collector_dedupe_lock_ttl_seconds)
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
            trust_env=False,
        ) as client:
            response = client.post("/collect", json=payload)
            if response.is_error:
                _raise_with_response_detail(response)
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
        if owner == owner_token:
            redis_client.delete(lock_key)


def run_index_daily_collection_request(
    market: str,
    request_id: str | None = None,
):
    normalized_market = str(market or "").strip().lower()
    if normalized_market not in {"hk", "us"}:
        raise ValueError("unsupported index collection market")

    endpoint = "/collect-index-hk-daily" if normalized_market == "hk" else "/collect-index-us-daily"
    return run_daily_collection_request(
        collector_key=f"index_{normalized_market}_daily",
        endpoint=endpoint,
        request_id=request_id,
        dedupe_lock_key=_index_temp_lock_key(normalized_market),
    )


def run_forex_collection_request(
    symbol_code: str,
    request_id: str | None = None,
):
    normalized_code = str(symbol_code or "").strip().upper()
    if not normalized_code:
        raise ValueError("symbol_code is required")

    lock_key = _forex_temp_lock_key(normalized_code)
    owner_token = request_id or f"manual:{uuid4()}"
    lock_acquired = redis_client.set(lock_key, owner_token, nx=True, ex=settings.collector_dedupe_lock_ttl_seconds)
    if not lock_acquired:
        return {
            "requested_at": date.today().isoformat(),
            "status": "deduplicated",
            "message": "same forex collection is already running",
        }

    try:
        with httpx.Client(
            base_url=settings.stock_temp_service_base_url,
            timeout=settings.stock_temp_service_timeout_seconds,
            trust_env=False,
        ) as client:
            max_attempts = max(1, int(settings.stock_temp_task_max_retries))
            for attempt in range(1, max_attempts + 1):
                response = client.post("/collect-forex", json={"symbol_code": normalized_code})
                if response.is_error:
                    if response.status_code >= 500 and attempt < max_attempts:
                        sleep_seconds = min(
                            30,
                            max(1, int(settings.collector_task_retry_backoff_seconds)) * attempt,
                        )
                        time.sleep(sleep_seconds)
                        continue
                    _raise_with_response_detail(response)
                response_json = response.json()
                upstream_status = str(response_json.get("status", "")).upper()
                if upstream_status not in {"SUCCESS", "UNCHANGED"}:
                    raise RuntimeError(f"unexpected forex collection status: {upstream_status or 'UNKNOWN'}")
                return {
                    "requested_at": date.today().isoformat(),
                    "status": "ok",
                    "symbol_code": normalized_code,
                    "upstream_status": upstream_status,
                    "upstream_response": response_json,
                }
    finally:
        owner = redis_client.get(lock_key)
        if owner == owner_token:
            redis_client.delete(lock_key)


def run_daily_collection_request(
    collector_key: str,
    endpoint: str,
    request_id: str | None = None,
    dedupe_lock_key: str | None = None,
):
    normalized_key = str(collector_key or "").strip().lower()
    normalized_endpoint = str(endpoint or "").strip()
    if not normalized_key:
        raise ValueError("collector_key is required")
    if not normalized_endpoint.startswith("/"):
        raise ValueError("endpoint must start with '/'")

    lock_key = dedupe_lock_key or _daily_temp_lock_key(normalized_key)
    owner_token = request_id or f"manual:{uuid4()}"
    lock_acquired = redis_client.set(lock_key, owner_token, nx=True, ex=settings.collector_dedupe_lock_ttl_seconds)
    if not lock_acquired:
        return {
            "requested_at": date.today().isoformat(),
            "status": "deduplicated",
            "message": "same daily collection is already running",
        }
    try:
        with httpx.Client(
            base_url=settings.stock_temp_service_base_url,
            timeout=settings.stock_temp_daily_service_timeout_seconds,
            trust_env=False,
        ) as client:
            max_attempts = max(1, int(settings.stock_temp_daily_task_max_retries))
            for attempt in range(1, max_attempts + 1):
                response = client.post(normalized_endpoint, json={})
                if response.is_error:
                    if response.status_code >= 500 and attempt < max_attempts:
                        sleep_seconds = min(
                            30,
                            max(1, int(settings.collector_task_retry_backoff_seconds)) * attempt,
                        )
                        time.sleep(sleep_seconds)
                        continue
                    _raise_with_response_detail(response)
                response_json = response.json()
                upstream_status = str(response_json.get("status", "")).upper()
                if upstream_status != "SUCCESS":
                    raise RuntimeError(f"unexpected daily collection status: {upstream_status or 'UNKNOWN'}")
                return {
                    "requested_at": date.today().isoformat(),
                    "status": "ok",
                    "collector_key": normalized_key,
                    "endpoint": normalized_endpoint,
                    "upstream_status": upstream_status,
                    "upstream_response": response_json,
                }
    finally:
        owner = redis_client.get(lock_key)
        if owner == owner_token:
            redis_client.delete(lock_key)


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
    return run_stock_data_collection_request(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        request_id=self.request.id,
    )


@celery_app.task(
    bind=True,
    name="tasks.collect_stock_hfq_data",
    autoretry_for=(httpx.HTTPError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.stock_temp_task_max_retries},
    soft_time_limit=settings.stock_temp_task_soft_time_limit_seconds,
    time_limit=settings.stock_temp_task_time_limit_seconds,
)
def collect_stock_hfq_data(
    self: Task,
    stock_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
):
    return run_stock_hfq_collection_request(
        stock_code=stock_code,
        start_date=start_date,
        end_date=end_date,
        request_id=self.request.id,
    )


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
    return run_stock_hfq_collection_request(
        stock_code=stock_code,
        start_date=start_date,
        end_date=end_date,
        request_id=self.request.id,
    )


@celery_app.task(
    bind=True,
    name="tasks.collect_index_hk_data",
    autoretry_for=(httpx.HTTPError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.stock_temp_task_max_retries},
    soft_time_limit=settings.stock_temp_task_soft_time_limit_seconds,
    time_limit=settings.stock_temp_task_time_limit_seconds,
)
def collect_index_hk_data(
    self: Task,
):
    return run_index_daily_collection_request(market="hk", request_id=self.request.id)


@celery_app.task(
    bind=True,
    name="tasks.collect_index_us_data",
    autoretry_for=(httpx.HTTPError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.stock_temp_task_max_retries},
    soft_time_limit=settings.stock_temp_task_soft_time_limit_seconds,
    time_limit=settings.stock_temp_task_time_limit_seconds,
)
def collect_index_us_data(
    self: Task,
):
    return run_index_daily_collection_request(market="us", request_id=self.request.id)
