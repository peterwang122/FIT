from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_user, require_root_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.progress import ProgressBoardPayload, ProgressBoardResponse
from app.services.progress_service import ProgressService


router = APIRouter()


@router.get("", response_model=ApiResponse[ProgressBoardResponse])
def get_progress_board(db: Session = Depends(get_db)):
    service = ProgressService(db)
    return ApiResponse(data=ProgressBoardResponse.model_validate(service.get_board()))


@router.put("", response_model=ApiResponse[ProgressBoardResponse])
def update_progress_board(
    payload: ProgressBoardPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_user),
):
    service = ProgressService(db)
    return ApiResponse(data=ProgressBoardResponse.model_validate(service.update_board(payload.model_dump(), current_user)))
