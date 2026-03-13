from datetime import date

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.stock import (
    CollectTaskPayload,
    DbStatusResponse,
    StockCandle,
    StockMetaResponse,
    StockSymbolResponse,
)
from app.services.stock_service import StockService
from app.services.task_idempotency_service import TaskIdempotencyService
from app.tasks.collector import collect_stock_data
from app.workers.celery_app import celery_app

router = APIRouter()


@router.get("/db-status", response_model=ApiResponse[DbStatusResponse])
def get_db_status(db: Session = Depends(get_db)):
    service = StockService(db)
    status = service.connection_status()
    return ApiResponse(data=DbStatusResponse.model_validate(status))


@router.get("/meta", response_model=ApiResponse[StockMetaResponse])
def get_stock_meta(db: Session = Depends(get_db)):
    service = StockService(db)
    return ApiResponse(
        data=StockMetaResponse(table_name=settings.stock_table_name, column_mapping=service.available_mapping())
    )


@router.get("/symbols", response_model=ApiResponse[list[StockSymbolResponse]])
def get_symbols(
    limit: int = Query(default=200, ge=1, le=5000),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    service = StockService(db)
    symbols = service.search_symbols(limit=limit, keyword=keyword)
    return ApiResponse(data=[StockSymbolResponse.model_validate(item) for item in symbols])


@router.get("/{ts_code}/kline", response_model=ApiResponse[list[StockCandle]])
def get_kline(
    ts_code: str,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    service = StockService(db)
    rows = service.list_daily_kline(ts_code=ts_code, start_date=start_date, end_date=end_date)
    return ApiResponse(data=[StockCandle.model_validate(row) for row in rows])


@router.post("/collect", response_model=ApiResponse[dict])
def submit_collect_task(payload: CollectTaskPayload, idempotency_key: str | None = Header(default=None)):
    idempotency_service = TaskIdempotencyService()
    if idempotency_key:
        existing_task_id = idempotency_service.get_existing_task_id(idempotency_key)
        if existing_task_id:
            return ApiResponse(data={"task_id": existing_task_id, "status": "deduplicated"})

    task = collect_stock_data.delay(
        ts_code=payload.ts_code,
        start_date=payload.start_date.isoformat() if payload.start_date else None,
        end_date=payload.end_date.isoformat() if payload.end_date else None,
    )

    if idempotency_key:
        idempotency_service.bind_task_id(idempotency_key, task.id)

    return ApiResponse(data={"task_id": task.id, "status": "submitted"})


@router.get("/collect/{task_id}", response_model=ApiResponse[dict])
def collect_task_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    return ApiResponse(
        data={
            "task_id": task_id,
            "state": result.state,
            "result": result.result if result.ready() else None,
        }
    )
