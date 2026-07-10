from fastapi import APIRouter, Depends, HTTPException

from app.api.deps.auth import require_non_guest_user
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
