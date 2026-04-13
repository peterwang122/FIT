import hashlib
import json
import logging
import re
from datetime import datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import redis_client
from app.core.security import generate_random_code, generate_session_id, hash_password, hash_sms_code, verify_password
from app.models.user import User
from app.models.user_session import UserSession


LOGGER = logging.getLogger(__name__)
PHONE_PATTERN = re.compile(r"^1\d{10}$")
DEFAULT_SMS_MINUTES = 5
DEFAULT_THEME = "system"
DEFAULT_LANGUAGE = "zh-CN"
DEFAULT_HOMEPAGE = "/"
DEFAULT_NOTIFICATIONS_ENABLED = True


def _utcnow() -> datetime:
    return datetime.utcnow()


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    @property
    def _session_ttl(self) -> int:
        return max(int(settings.auth_session_ttl_seconds), 60)

    def _session_key(self, session_id: str) -> str:
        return f"fit:auth:session:{session_id}"

    def _code_key(self, phone: str) -> str:
        return f"fit:auth:sms_code:{phone}"

    def _cooldown_key(self, phone: str) -> str:
        return f"fit:auth:sms_cooldown:{phone}"

    def _daily_key(self, phone: str) -> str:
        today = _utcnow().strftime("%Y-%m-%d")
        return f"fit:auth:sms_daily:{phone}:{today}"

    def _session_expires_at(self) -> datetime:
        return _utcnow() + timedelta(seconds=self._session_ttl)

    def _hash_session_id(self, session_id: str) -> str:
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()

    def _client_ip(self, request: Request | None) -> str:
        if request is None:
            return ""
        forwarded_for = request.headers.get("x-forwarded-for", "").strip()
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.client.host if request.client else ""

    def _user_agent(self, request: Request | None) -> str:
        if request is None:
            return ""
        return request.headers.get("user-agent", "").strip()

    def _set_session_cookie(self, response: Response, session_id: str) -> None:
        response.set_cookie(
            key=settings.auth_session_cookie_name,
            value=session_id,
            max_age=self._session_ttl,
            httponly=True,
            secure=settings.auth_cookie_secure,
            samesite=settings.auth_cookie_samesite,
            path="/",
        )

    def _delete_session_cookie(self, response: Response) -> None:
        response.delete_cookie(
            key=settings.auth_session_cookie_name,
            path="/",
            samesite=settings.auth_cookie_samesite,
        )

    def _serialize_user(self, user: User) -> dict:
        return {
            "id": user.id,
            "username": user.username,
            "phone": user.phone,
            "role": user.role,
            "has_password": bool(user.password_hash),
            "nickname": user.nickname or "",
            "email": user.email,
            "company": user.company or "",
            "bio": user.bio or "",
            "created_at": user.created_at,
            "last_login_at": user.last_login_at,
            "preferences": {
                "theme": user.theme_preference or DEFAULT_THEME,
                "language": user.language_preference or DEFAULT_LANGUAGE,
                "notifications_enabled": bool(user.notifications_enabled),
                "default_homepage": user.default_homepage or DEFAULT_HOMEPAGE,
            },
        }

    def _serialize_session_record(self, item: UserSession, current_hash: str | None = None) -> dict:
        is_current = bool(current_hash and item.session_id_hash == current_hash)
        is_active = item.revoked_at is None and bool(item.expires_at and item.expires_at > _utcnow())
        return {
            "id": item.id,
            "user_agent": item.user_agent or "",
            "ip_address": item.ip_address or "",
            "created_at": item.created_at,
            "last_seen_at": item.last_seen_at,
            "expires_at": item.expires_at,
            "revoked_at": item.revoked_at,
            "is_current": is_current,
            "is_active": is_active,
        }

    def validate_phone(self, phone: str) -> str:
        normalized = phone.strip()
        if not PHONE_PATTERN.match(normalized):
            raise ValueError("请输入有效的 11 位手机号")
        return normalized

    def get_user_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_user_by_account(self, account: str) -> User | None:
        normalized = account.strip()
        if not normalized:
            return None
        return (
            self.db.query(User)
            .filter(or_(User.username == normalized, User.phone == normalized))
            .order_by(User.id.asc())
            .first()
        )

    def search_regular_users(self, keyword: str, current_user: User, limit: int = 20) -> list[dict]:
        if current_user.role != "root":
            raise ValueError("forbidden")
        normalized = keyword.strip()
        query = self.db.query(User).filter(User.role == "user")
        if normalized:
            like_value = f"%{normalized}%"
            query = query.filter(or_(User.username.like(like_value), User.phone.like(like_value), User.nickname.like(like_value)))
        items = query.order_by(User.last_login_at.desc(), User.created_at.desc()).limit(max(limit, 1)).all()
        return [
            {
                "id": item.id,
                "username": item.username,
                "phone": item.phone,
                "nickname": item.nickname or "",
                "role": item.role,
            }
            for item in items
            if item.id != current_user.id
        ]

    def get_or_create_user_by_phone(self, phone: str) -> User:
        normalized_phone = self.validate_phone(phone)
        user = self.db.query(User).filter(User.phone == normalized_phone).first()
        if user is not None:
            if not user.username:
                user.username = normalized_phone
                self.db.add(user)
                self.db.commit()
                self.db.refresh(user)
            return user

        user = User(
            username=normalized_phone,
            phone=normalized_phone,
            password_hash=None,
            role="user",
            nickname="",
            email=None,
            company="",
            bio="",
            theme_preference=DEFAULT_THEME,
            language_preference=DEFAULT_LANGUAGE,
            notifications_enabled=DEFAULT_NOTIFICATIONS_ENABLED,
            default_homepage=DEFAULT_HOMEPAGE,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def _send_with_aliyun(self, phone: str, code: str) -> None:
        access_key_id = settings.alibaba_cloud_access_key_id or settings.aliyun_sms_access_key_id
        access_key_secret = settings.alibaba_cloud_access_key_secret or settings.aliyun_sms_access_key_secret
        if not (
            access_key_id
            and access_key_secret
            and settings.aliyun_sms_sign_name
            and settings.aliyun_sms_template_code
        ):
            if settings.app_debug or settings.app_env != "prod":
                LOGGER.warning("SMS debug fallback for %s: %s", phone, code)
                return
            raise RuntimeError("短信服务未配置")

        try:
            from alibabacloud_credentials.client import Client as CredentialClient
            from alibabacloud_credentials.models import Config as CredentialConfig
            from alibabacloud_dypnsapi20170525 import models as dypnsapi_models
            from alibabacloud_dypnsapi20170525.client import Client as DypnsapiClient
            from alibabacloud_tea_openapi import models as open_api_models
            from alibabacloud_tea_util import models as util_models
        except ImportError as exc:
            if settings.app_debug or settings.app_env != "prod":
                LOGGER.warning("Aliyun SMS SDK unavailable, falling back to debug logging: %s", exc)
                LOGGER.warning("SMS debug fallback for %s: %s", phone, code)
                return
            raise RuntimeError("短信依赖未安装，请安装阿里云短信 SDK") from exc

        credential_config = CredentialConfig(
            type="access_key",
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
        )
        credential_client = CredentialClient(credential_config)
        config = open_api_models.Config(credential=credential_client, endpoint="dypnsapi.aliyuncs.com")
        client = DypnsapiClient(config)
        request = dypnsapi_models.SendSmsVerifyCodeRequest(
            sign_name=settings.aliyun_sms_sign_name,
            template_code=settings.aliyun_sms_template_code,
            phone_number=phone,
            template_param=json.dumps({"code": code, "min": str(DEFAULT_SMS_MINUTES)}, ensure_ascii=False),
        )
        runtime = util_models.RuntimeOptions()
        response = client.send_sms_verify_code_with_options(request, runtime)
        body = getattr(response, "body", None)
        response_code = getattr(body, "code", "") if body is not None else ""
        if response_code != "OK":
            message = getattr(body, "message", "短信发送失败") if body is not None else "短信发送失败"
            raise RuntimeError(f"短信发送失败: {message}")

    def send_sms_code(self, phone: str) -> None:
        normalized_phone = self.validate_phone(phone)
        if redis_client.exists(self._cooldown_key(normalized_phone)):
            raise ValueError("验证码发送过于频繁，请稍后再试")

        daily_key = self._daily_key(normalized_phone)
        daily_count = redis_client.get(daily_key)
        if daily_count is not None and int(daily_count) >= settings.auth_sms_daily_limit:
            raise ValueError("今日验证码发送次数已达上限")

        code = generate_random_code()
        payload = {"code_hash": hash_sms_code(normalized_phone, code), "attempts_left": settings.auth_sms_max_attempts}
        redis_client.setex(self._code_key(normalized_phone), settings.auth_sms_code_ttl_seconds, json.dumps(payload))
        redis_client.setex(self._cooldown_key(normalized_phone), settings.auth_sms_resend_cooldown_seconds, "1")
        if daily_count is None:
            redis_client.setex(daily_key, 86400, "1")
        else:
            redis_client.incr(daily_key)

        self._send_with_aliyun(normalized_phone, code)

    def _consume_sms_code(self, phone: str, code: str) -> None:
        normalized_phone = self.validate_phone(phone)
        cached = redis_client.get(self._code_key(normalized_phone))
        if not cached:
            raise ValueError("验证码已失效，请重新获取")

        try:
            payload = json.loads(cached)
        except json.JSONDecodeError as exc:
            redis_client.delete(self._code_key(normalized_phone))
            raise ValueError("验证码已失效，请重新获取") from exc

        expected_hash = str(payload.get("code_hash", "")).strip()
        attempts_left = int(payload.get("attempts_left", settings.auth_sms_max_attempts))
        if expected_hash != hash_sms_code(normalized_phone, code.strip()):
            attempts_left -= 1
            if attempts_left <= 0:
                redis_client.delete(self._code_key(normalized_phone))
                raise ValueError("验证码错误次数过多，请重新获取")
            payload["attempts_left"] = attempts_left
            ttl = redis_client.ttl(self._code_key(normalized_phone))
            redis_client.setex(self._code_key(normalized_phone), max(ttl, 1), json.dumps(payload))
            raise ValueError(f"验证码错误，还可尝试 {attempts_left} 次")

        redis_client.delete(self._code_key(normalized_phone))

    def _store_session(self, session_id: str, user: User) -> None:
        redis_client.setex(self._session_key(session_id), self._session_ttl, json.dumps({"user_id": user.id}))

    def _record_session_login(self, session_id: str, user: User, request: Request | None) -> None:
        expires_at = self._session_expires_at()
        item = UserSession(
            user_id=user.id,
            session_id_hash=self._hash_session_id(session_id),
            user_agent=self._user_agent(request),
            ip_address=self._client_ip(request),
            expires_at=expires_at,
            last_seen_at=_utcnow(),
        )
        self.db.add(item)
        self.db.commit()

    def _touch_session_record(self, session_id: str, user: User, request: Request | None = None) -> None:
        session_hash = self._hash_session_id(session_id)
        item = (
            self.db.query(UserSession)
            .filter(UserSession.user_id == user.id, UserSession.session_id_hash == session_hash)
            .first()
        )
        if item is None:
            self._record_session_login(session_id, user, request)
            return
        item.last_seen_at = _utcnow()
        item.expires_at = self._session_expires_at()
        if request is not None:
            user_agent = self._user_agent(request)
            ip_address = self._client_ip(request)
            if user_agent:
                item.user_agent = user_agent
            if ip_address:
                item.ip_address = ip_address
        self.db.add(item)
        self.db.commit()

    def _revoke_session_record(self, session_id: str | None, user_id: int | None = None) -> None:
        if not session_id:
            return
        session_hash = self._hash_session_id(session_id)
        query = self.db.query(UserSession).filter(UserSession.session_id_hash == session_hash)
        if user_id is not None:
            query = query.filter(UserSession.user_id == user_id)
        item = query.first()
        if item is None:
            return
        item.revoked_at = _utcnow()
        item.expires_at = min(item.expires_at, _utcnow()) if item.expires_at else _utcnow()
        self.db.add(item)
        self.db.commit()

    def login_user(self, user: User, response: Response, request: Request | None = None) -> dict:
        session_id = generate_session_id()
        user.last_login_at = _utcnow()
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        self._store_session(session_id, user)
        self._record_session_login(session_id, user, request)
        self._set_session_cookie(response, session_id)
        return {"user": self._serialize_user(user)}

    def login_with_sms(self, phone: str, code: str, response: Response, request: Request | None = None) -> dict:
        self._consume_sms_code(phone, code)
        user = self.get_or_create_user_by_phone(phone)
        return self.login_user(user, response, request)

    def login_with_account(self, account: str, password: str, response: Response, request: Request | None = None) -> dict:
        user = self.get_user_by_account(account)
        if user is None:
            raise ValueError("账号或密码不正确")
        if not user.password_hash:
            raise ValueError("该账号尚未设置密码，请先使用验证码登录后设置密码")
        if not verify_password(password, user.password_hash):
            raise ValueError("账号或密码不正确")
        return self.login_user(user, response, request)

    def login_guest(self, response: Response, request: Request | None = None) -> dict:
        user = self.get_user_by_account(settings.guest_username)
        if user is None:
            raise ValueError("游客账号未初始化")
        return self.login_user(user, response, request)

    def get_user_from_session(self, session_id: str) -> User | None:
        cached = redis_client.get(self._session_key(session_id))
        if not cached:
            return None
        try:
            payload = json.loads(cached)
            user_id = int(payload.get("user_id"))
        except (TypeError, ValueError, json.JSONDecodeError):
            redis_client.delete(self._session_key(session_id))
            return None
        user = self.get_user_by_id(user_id)
        if user is None:
            redis_client.delete(self._session_key(session_id))
            return None
        return user

    def refresh_session(self, session_id: str, response: Response, user: User, request: Request | None = None) -> None:
        self._store_session(session_id, user)
        self._touch_session_record(session_id, user, request)
        self._set_session_cookie(response, session_id)

    def logout(self, session_id: str | None, response: Response) -> None:
        if session_id:
            redis_client.delete(self._session_key(session_id))
            self._revoke_session_record(session_id)
        self._delete_session_cookie(response)

    def set_password(self, user: User, password: str, current_password: str | None = None) -> dict:
        if user.role == "guest":
            raise ValueError("游客账号不支持修改密码")
        normalized = password.strip()
        if len(normalized) < 6:
            raise ValueError("密码长度至少为 6 位")
        if user.password_hash and (not current_password or not verify_password(current_password, user.password_hash)):
            raise ValueError("当前密码不正确")
        user.password_hash = hash_password(normalized)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return {"user": self._serialize_user(user)}

    def update_profile(self, user: User, payload: dict) -> dict:
        user.nickname = str(payload.get("nickname", user.nickname or "")).strip()
        email = str(payload.get("email", user.email or "")).strip()
        user.email = email or None
        user.company = str(payload.get("company", user.company or "")).strip()
        user.bio = str(payload.get("bio", user.bio or "")).strip()
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return {"user": self._serialize_user(user)}

    def update_preferences(self, user: User, payload: dict) -> dict:
        user.theme_preference = str(payload.get("theme", user.theme_preference or DEFAULT_THEME)).strip() or DEFAULT_THEME
        user.language_preference = (
            str(payload.get("language", user.language_preference or DEFAULT_LANGUAGE)).strip() or DEFAULT_LANGUAGE
        )
        user.notifications_enabled = bool(payload.get("notifications_enabled", user.notifications_enabled))
        user.default_homepage = (
            str(payload.get("default_homepage", user.default_homepage or DEFAULT_HOMEPAGE)).strip() or DEFAULT_HOMEPAGE
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return {"user": self._serialize_user(user)}

    def list_sessions(self, user: User, current_session_id: str | None) -> list[dict]:
        current_hash = self._hash_session_id(current_session_id) if current_session_id else None
        items = (
            self.db.query(UserSession)
            .filter(UserSession.user_id == user.id)
            .order_by(UserSession.last_seen_at.desc(), UserSession.created_at.desc())
            .all()
        )
        return [self._serialize_session_record(item, current_hash) for item in items]

    def revoke_session(self, user: User, session_record_id: int, current_session_id: str | None, response: Response) -> dict:
        item = (
            self.db.query(UserSession)
            .filter(UserSession.id == session_record_id, UserSession.user_id == user.id)
            .first()
        )
        if item is None:
            raise ValueError("session not found")
        item.revoked_at = _utcnow()
        item.expires_at = min(item.expires_at, _utcnow()) if item.expires_at else _utcnow()
        self.db.add(item)
        self.db.commit()

        if current_session_id and item.session_id_hash == self._hash_session_id(current_session_id):
            redis_client.delete(self._session_key(current_session_id))
            self._delete_session_cookie(response)
        return self._serialize_session_record(item, self._hash_session_id(current_session_id) if current_session_id else None)
