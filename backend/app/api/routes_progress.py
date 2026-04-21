from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_user_optional, require_root_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.progress import ProgressBoardPayload, ProgressBoardResponse, ProgressDraftPayload, ProgressTodoPayload
from app.services.progress_service import ProgressService

router = APIRouter()


@router.get("", response_model=ApiResponse[ProgressBoardResponse])
def get_progress_board(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    service = ProgressService(db)
    return ApiResponse(data=ProgressBoardResponse.model_validate(service.get_board(current_user)))


@router.put("/todo", response_model=ApiResponse[ProgressBoardResponse])
def update_progress_todo(
    payload: ProgressTodoPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_user),
):
    service = ProgressService(db)
    board = service.update_todo_items(payload.todo_items, current_user)
    return ApiResponse(data=ProgressBoardResponse.model_validate(board))


@router.put("/draft", response_model=ApiResponse[ProgressBoardResponse])
def update_progress_draft(
    payload: ProgressDraftPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_user),
):
    service = ProgressService(db)
    board = service.update_draft_progress(payload.draft_progress_days, payload.generation_meta, current_user)
    return ApiResponse(data=ProgressBoardResponse.model_validate(board))


@router.post("/publish", response_model=ApiResponse[ProgressBoardResponse])
def publish_progress_board(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_user),
):
    service = ProgressService(db)
    return ApiResponse(data=ProgressBoardResponse.model_validate(service.publish_draft(current_user)))


@router.post("/reset", response_model=ApiResponse[ProgressBoardResponse])
def reset_progress_board(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_user),
):
    service = ProgressService(db)
    return ApiResponse(data=ProgressBoardResponse.model_validate(service.reset_board(current_user)))


@router.put("", response_model=ApiResponse[ProgressBoardResponse])
def update_progress_board_legacy(
    payload: ProgressBoardPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_user),
):
    service = ProgressService(db)
    board = service.update_todo_items(payload.todo_items, current_user)
    return ApiResponse(data=ProgressBoardResponse.model_validate(board))
