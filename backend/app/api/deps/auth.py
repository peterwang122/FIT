from fastapi import Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import AuthService


def get_current_user(
    request: Request,
    response: Response,
    session_id: str | None = Cookie(default=None, alias=settings.auth_session_cookie_name),
    db: Session = Depends(get_db),
) -> User:
    if not session_id:
        raise HTTPException(status_code=401, detail="请先登录")
    service = AuthService(db)
    user = service.get_user_from_session(session_id)
    if user is None:
        service.logout(session_id, response)
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    service.refresh_session(session_id, response, user, request)
    return user


def require_authenticated_user(_: User = Depends(get_current_user)) -> None:
    return None


def require_root_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "root":
        raise HTTPException(status_code=403, detail="仅 root 用户可执行该操作")
    return current_user
