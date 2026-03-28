from datetime import date

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.stock import (
    CollectTaskPayload,
    DbStatusResponse,
    IndexDashboardResponse,
    FuturesBasisPointResponse,
    IndexEmotionPointResponse,
    IndexBreadthPointResponse,
    MarketOptionResponse,
    NetPositionSeriesResponse,
    NetPositionTablesResponse,
    QfqCollectTaskPayload,
    QuantEquityCurveResponse,
    QuantStrategyConfigResponse,
    QuantStrategySavePayload,
    StockCandle,
    StockMetaResponse,
    StockSymbolResponse,
)
from app.services.quant_service import QuantService
from app.services.stock_service import StockService
from app.services.task_idempotency_service import TaskIdempotencyService
from app.tasks.collector import collect_stock_data, collect_stock_qfq_data
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


@router.get("/index-emotions", response_model=ApiResponse[list[IndexEmotionPointResponse]])
def get_index_emotions(db: Session = Depends(get_db)):
    service = StockService(db)
    items = service.list_excel_index_emotions()
    return ApiResponse(data=[IndexEmotionPointResponse.model_validate(item) for item in items])


@router.get("/index-futures-basis", response_model=ApiResponse[list[FuturesBasisPointResponse]])
def get_index_futures_basis(db: Session = Depends(get_db)):
    service = StockService(db)
    items = service.list_index_futures_basis()
    return ApiResponse(data=[FuturesBasisPointResponse.model_validate(item) for item in items])


@router.get("/quant/index-breadth", response_model=ApiResponse[list[IndexBreadthPointResponse]])
def get_index_breadth(db: Session = Depends(get_db)):
    service = QuantService(db)
    items = service.list_index_breadth()
    return ApiResponse(data=[IndexBreadthPointResponse.model_validate(item) for item in items])


@router.get("/quant/index-dashboard", response_model=ApiResponse[IndexDashboardResponse])
def get_index_dashboard(
    index_code: str = Query(..., min_length=1),
    mode: str = Query(default="recent"),
    db: Session = Depends(get_db),
):
    service = QuantService(db)
    try:
        item = service.get_index_dashboard(index_code=index_code, mode=mode)
    except ValueError as exc:
        detail = str(exc)
        status_code = 400 if "mode" in detail else 404
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ApiResponse(data=IndexDashboardResponse.model_validate(item))


@router.get("/quant/strategies", response_model=ApiResponse[list[QuantStrategyConfigResponse]])
def get_quant_strategies(db: Session = Depends(get_db)):
    service = QuantService(db)
    items = service.list_strategies()
    return ApiResponse(data=[QuantStrategyConfigResponse.model_validate(item) for item in items])


@router.post("/quant/strategies", response_model=ApiResponse[QuantStrategyConfigResponse])
def create_quant_strategy(payload: QuantStrategySavePayload, db: Session = Depends(get_db)):
    service = QuantService(db)
    item = service.create_strategy(payload.model_dump())
    return ApiResponse(data=QuantStrategyConfigResponse.model_validate(item))


@router.put("/quant/strategies/{strategy_id}", response_model=ApiResponse[QuantStrategyConfigResponse])
def update_quant_strategy(strategy_id: int, payload: QuantStrategySavePayload, db: Session = Depends(get_db)):
    service = QuantService(db)
    try:
        item = service.update_strategy(strategy_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=QuantStrategyConfigResponse.model_validate(item))


@router.delete("/quant/strategies/{strategy_id}", response_model=ApiResponse[dict])
def delete_quant_strategy(strategy_id: int, db: Session = Depends(get_db)):
    service = QuantService(db)
    try:
        service.delete_strategy(strategy_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data={"id": strategy_id, "status": "deleted"})


@router.get("/quant/strategies/{strategy_id}/equity-curve", response_model=ApiResponse[QuantEquityCurveResponse])
def get_quant_strategy_equity_curve(strategy_id: int, db: Session = Depends(get_db)):
    service = QuantService(db)
    try:
        item = service.calculate_equity_curve(strategy_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=QuantEquityCurveResponse.model_validate(item))


@router.get("/cffex/net-positions", response_model=ApiResponse[NetPositionTablesResponse])
def get_cffex_net_positions(
    trade_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    service = StockService(db)
    try:
        items = service.get_cffex_net_position_tables(trade_date=trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=NetPositionTablesResponse.model_validate(items))


@router.get("/cffex/net-position-series", response_model=ApiResponse[NetPositionSeriesResponse])
def get_cffex_net_position_series(db: Session = Depends(get_db)):
    service = StockService(db)
    items = service.get_cffex_net_position_series()
    return ApiResponse(data=NetPositionSeriesResponse.model_validate(items))


@router.get("/indexes/options", response_model=ApiResponse[list[MarketOptionResponse]])
def get_index_options(db: Session = Depends(get_db)):
    service = StockService(db)
    items = service.list_index_options()
    return ApiResponse(data=[MarketOptionResponse.model_validate(item) for item in items])


@router.get("/indexes/{index_code}/kline", response_model=ApiResponse[list[StockCandle]])
def get_index_kline(
    index_code: str,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    service = StockService(db)
    rows = service.list_index_daily_kline(index_code=index_code, start_date=start_date, end_date=end_date)
    return ApiResponse(data=[StockCandle.model_validate(row) for row in rows])


@router.get("/forex/options", response_model=ApiResponse[list[MarketOptionResponse]])
def get_forex_options(db: Session = Depends(get_db)):
    service = StockService(db)
    items = service.list_forex_options()
    return ApiResponse(data=[MarketOptionResponse.model_validate(item) for item in items])


@router.get("/forex/{symbol_code}/kline", response_model=ApiResponse[list[StockCandle]])
def get_forex_kline(
    symbol_code: str,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    service = StockService(db)
    rows = service.list_forex_daily_kline(symbol_code=symbol_code, start_date=start_date, end_date=end_date)
    return ApiResponse(data=[StockCandle.model_validate(row) for row in rows])


@router.get("/{ts_code}/qfq-kline", response_model=ApiResponse[list[StockCandle]])
def get_qfq_kline(
    ts_code: str,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    service = StockService(db)
    rows = service.list_qfq_daily_kline(ts_code=ts_code, start_date=start_date, end_date=end_date)
    return ApiResponse(data=[StockCandle.model_validate(row) for row in rows])


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


@router.post("/qfq-collect", response_model=ApiResponse[dict])
def submit_qfq_collect_task(payload: QfqCollectTaskPayload, idempotency_key: str | None = Header(default=None)):
    idempotency_service = TaskIdempotencyService()
    if idempotency_key:
        existing_task_id = idempotency_service.get_existing_task_id(idempotency_key)
        if existing_task_id:
            return ApiResponse(data={"task_id": existing_task_id, "status": "deduplicated"})

    task = collect_stock_qfq_data.delay(
        stock_code=payload.ts_code,
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


@router.get("/qfq-collect/{task_id}", response_model=ApiResponse[dict])
def qfq_collect_task_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    return ApiResponse(
        data={
            "task_id": task_id,
            "state": result.state,
            "result": result.result if result.ready() else None,
        }
    )
