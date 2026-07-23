from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps.auth import require_non_guest_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.research_service import ResearchService


router = APIRouter()


@router.get("/vix-option-analysis", response_model=ApiResponse[dict])
def get_vix_option_analysis(_: User = Depends(require_non_guest_user)):
    try:
        payload = ResearchService().get_vix_option_analysis()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ApiResponse(data=payload)


@router.get("/csi1000-futures-analysis", response_model=ApiResponse[dict])
def get_csi1000_futures_analysis(
    _: User = Depends(require_non_guest_user),
):
    try:
        payload = ResearchService().get_csi1000_futures_analysis()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ApiResponse(data=payload)


@router.get("/vix-option-analysis/contracts/{contract_code}/candles", response_model=ApiResponse[dict])
def get_vix_option_contract_candles(
    contract_code: str,
    exchange: str = Query(...),
    _: User = Depends(require_non_guest_user),
    db: Session = Depends(get_db),
):
    try:
        payload = ResearchService(db).get_option_contract_candles(exchange, contract_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ApiResponse(data=payload)
