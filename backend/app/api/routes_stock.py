from datetime import date

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.stock import CollectTaskPayload, StockCandle
from app.services.stock_service import StockService
from app.tasks.collector import collect_stock_data
from app.workers.celery_app import celery_app

router = APIRouter()


@router.get("/{ts_code}/kline", response_model=ApiResponse[list[StockCandle]])
def get_kline(
    ts_code: str,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=500, le=3000),
    db: Session = Depends(get_db),
):
    service = StockService(db)
    rows = service.list_daily_kline(ts_code=ts_code, start_date=start_date, end_date=end_date, limit=limit)
    return ApiResponse(data=[StockCandle.model_validate(row, from_attributes=True) for row in rows])


@router.post("/collect", response_model=ApiResponse[dict])
def submit_collect_task(payload: CollectTaskPayload):
    task = collect_stock_data.delay(
        ts_code=payload.ts_code,
        start_date=payload.start_date.isoformat() if payload.start_date else None,
        end_date=payload.end_date.isoformat() if payload.end_date else None,
    )
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
