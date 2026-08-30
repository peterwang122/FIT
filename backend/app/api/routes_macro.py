from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.services.macro_service import MacroService


router = APIRouter()


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
