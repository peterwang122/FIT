from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.services.macro_service import MacroService
from app.schemas.market_regime import MarketRegimeResponse, RegimeIndex
from app.services.market_regime_service import get_market_regime
from app.services.market_regime_research import read_observations, select_macro, macro_derived, macro_completeness


router = APIRouter()


@router.get("/market-regime/macro-evidence", response_model=ApiResponse[dict])
def get_market_regime_macro_evidence(
    as_of_at: datetime = Query(..., description="上海时间的已知数据截止时点"),
    db: Session = Depends(get_db),
):
    from zoneinfo import ZoneInfo
    if as_of_at.tzinfo is not None:
        as_of_at = as_of_at.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    if as_of_at > datetime.now():
        raise HTTPException(status_code=400, detail="不能查询未来的已知数据")
    observations = read_observations(db)
    evidence = select_macro(observations, as_of_at)
    missing, stale = macro_completeness(evidence)
    return ApiResponse(data={"as_of_at": as_of_at, "timezone": "Asia/Shanghai",
                             "research_only": True, "model_approved": False,
                             "macro_evidence": evidence, "derived_evidence": macro_derived(evidence),
                             "archive_macro_evidence": select_macro(observations, as_of_at, strict=False),
                             "missing_macro": missing, "stale_macro": stale,
                             "macro_complete": not (missing or stale)})


@router.get("/market-regime", response_model=ApiResponse[MarketRegimeResponse])
def get_market_regime_dashboard(
    index_code: RegimeIndex = Query(default="sh000852"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    try:
        payload = get_market_regime(index_code, start_date, end_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ApiResponse(data=payload)


@router.get("/dashboard", response_model=ApiResponse[dict])
def get_macro_dashboard(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    try:
        payload = MacroService(db).get_dashboard(start_date=start_date, end_date=end_date)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ApiResponse(data=payload)


@router.get("/bank-liquidity", response_model=ApiResponse[dict])
def get_bank_liquidity_dashboard(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    try:
        payload = MacroService(db).get_bank_liquidity(
            start_date=start_date,
            end_date=end_date,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ApiResponse(data=payload)
