from fastapi import APIRouter, Depends, HTTPException

from app.api.deps.auth import require_root_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.system import PhddnsWatchdogStatusResponse, PhddnsWatchdogTogglePayload
from app.services.system_service import PhddnsWatchdogService


router = APIRouter()


@router.get("/phddns-watchdog", response_model=ApiResponse[PhddnsWatchdogStatusResponse])
def get_phddns_watchdog_status(_: User = Depends(require_root_user)):
    service = PhddnsWatchdogService()
    return ApiResponse(data=PhddnsWatchdogStatusResponse.model_validate(service.status()))


@router.put("/phddns-watchdog", response_model=ApiResponse[PhddnsWatchdogStatusResponse])
def update_phddns_watchdog(
    payload: PhddnsWatchdogTogglePayload,
    _: User = Depends(require_root_user),
):
    service = PhddnsWatchdogService()
    try:
        item = service.set_enabled(payload.enabled)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ApiResponse(data=PhddnsWatchdogStatusResponse.model_validate(item))
