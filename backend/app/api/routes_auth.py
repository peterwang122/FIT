from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    AccountLoginPayload,
    AuthSessionRecordResponse,
    AuthSessionResponse,
    AuthStatusResponse,
    SendSmsCodePayload,
    SetPasswordPayload,
    SmsLoginPayload,
    UpdatePreferencesPayload,
    UpdateProfilePayload,
    UserSearchResultResponse,
)
from app.schemas.common import ApiResponse
from app.services.auth_service import AuthService


router = APIRouter()


@router.post("/sms/send-code", response_model=ApiResponse[AuthStatusResponse])
def send_sms_code(payload: SendSmsCodePayload, db: Session = Depends(get_db)):
    service = AuthService(db)
    try:
        service.send_sms_code(payload.phone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ApiResponse(data=AuthStatusResponse(status="sent"))


@router.post("/sms/login", response_model=ApiResponse[AuthSessionResponse])
def sms_login(payload: SmsLoginPayload, request: Request, response: Response, db: Session = Depends(get_db)):
    service = AuthService(db)
    try:
        item = service.login_with_sms(payload.phone, payload.code, response, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(data=AuthSessionResponse.model_validate(item))


@router.post("/account/login", response_model=ApiResponse[AuthSessionResponse])
def account_login(payload: AccountLoginPayload, request: Request, response: Response, db: Session = Depends(get_db)):
    service = AuthService(db)
    try:
        item = service.login_with_account(payload.account, payload.password, response, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(data=AuthSessionResponse.model_validate(item))


@router.post("/guest/login", response_model=ApiResponse[AuthSessionResponse])
def guest_login(request: Request, response: Response, db: Session = Depends(get_db)):
    service = AuthService(db)
    try:
        item = service.login_guest(response, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(data=AuthSessionResponse.model_validate(item))


@router.get("/me", response_model=ApiResponse[AuthSessionResponse])
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service = AuthService(db)
    return ApiResponse(data=AuthSessionResponse(user=service._serialize_user(current_user)))


@router.post("/logout", response_model=ApiResponse[AuthStatusResponse])
def logout(
    response: Response,
    session_id: str | None = Cookie(default=None, alias=settings.auth_session_cookie_name),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    service.logout(session_id, response)
    return ApiResponse(data=AuthStatusResponse(status=f"logged_out:{current_user.username}"))


@router.post("/password/set", response_model=ApiResponse[AuthSessionResponse])
def set_password(
    payload: SetPasswordPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    try:
        item = service.set_password(current_user, payload.password, payload.current_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(data=AuthSessionResponse.model_validate(item))


@router.patch("/profile", response_model=ApiResponse[AuthSessionResponse])
@router.put("/profile", response_model=ApiResponse[AuthSessionResponse])
def update_profile(
    payload: UpdateProfilePayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    item = service.update_profile(current_user, payload.model_dump())
    return ApiResponse(data=AuthSessionResponse.model_validate(item))


@router.patch("/preferences", response_model=ApiResponse[AuthSessionResponse])
@router.put("/preferences", response_model=ApiResponse[AuthSessionResponse])
def update_preferences(
    payload: UpdatePreferencesPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    item = service.update_preferences(current_user, payload.model_dump())
    return ApiResponse(data=AuthSessionResponse.model_validate(item))


@router.get("/sessions", response_model=ApiResponse[list[AuthSessionRecordResponse]])
def get_sessions(
    session_id: str | None = Cookie(default=None, alias=settings.auth_session_cookie_name),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    items = service.list_sessions(current_user, session_id)
    return ApiResponse(data=[AuthSessionRecordResponse.model_validate(item) for item in items])


@router.post("/sessions/{session_record_id}/revoke", response_model=ApiResponse[AuthSessionRecordResponse])
def revoke_session(
    session_record_id: int,
    response: Response,
    session_id: str | None = Cookie(default=None, alias=settings.auth_session_cookie_name),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    try:
        item = service.revoke_session(current_user, session_record_id, session_id, response)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=AuthSessionRecordResponse.model_validate(item))


@router.get("/users/search", response_model=ApiResponse[list[UserSearchResultResponse]])
def search_users(
    keyword: str = Query(default="", min_length=0, max_length=64),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    try:
        items = service.search_regular_users(keyword, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return ApiResponse(data=[UserSearchResultResponse.model_validate(item) for item in items])
