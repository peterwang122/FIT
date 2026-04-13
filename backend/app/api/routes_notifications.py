from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.notification import NotificationListResponse, UserNotificationResponse
from app.services.notification_service import NotificationService

router = APIRouter()


@router.get("", response_model=ApiResponse[NotificationListResponse])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = NotificationService(db)
    item = service.list_notifications(current_user.id)
    return ApiResponse(data=NotificationListResponse.model_validate(item))


@router.post("/read-all", response_model=ApiResponse[NotificationListResponse])
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = NotificationService(db)
    item = service.mark_all_read(current_user.id)
    return ApiResponse(data=NotificationListResponse.model_validate(item))


@router.post("/{notification_id}/read", response_model=ApiResponse[UserNotificationResponse])
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = NotificationService(db)
    try:
        item = service.mark_read(notification_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=UserNotificationResponse.model_validate(item))
