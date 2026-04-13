from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_user, require_root_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.task import (
    RootVisibleStrategyResponse,
    ScheduledTaskResponse,
    ScheduledTaskRunResponse,
    TaskCreatePayload,
    TaskTogglePayload,
    TaskUpdatePayload,
)
from app.services.task_service import TaskService
from app.tasks.scheduler import execute_scheduled_task_run

router = APIRouter()


def _handle_task_exception(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _rewrite_flower_html(content: str) -> str:
    proxy_prefix = f"{settings.api_prefix}/tasks/monitor/flower"
    replacements = {
        'href="/': f'href="{proxy_prefix}/',
        "href='/": f"href='{proxy_prefix}/",
        'src="/': f'src="{proxy_prefix}/',
        "src='/": f"src='{proxy_prefix}/",
        'action="/': f'action="{proxy_prefix}/',
        "action='/": f"action='{proxy_prefix}/",
        'url(/': f'url({proxy_prefix}/',
        'fetch("/': f'fetch("{proxy_prefix}/',
        "fetch('/": f"fetch('{proxy_prefix}/",
    }
    for source, target in replacements.items():
        content = content.replace(source, target)
    return content


async def _proxy_flower(path: str, request: Request) -> Response:
    upstream_base = settings.flower_url.rstrip("/")
    upstream_url = f"{upstream_base}/{path.lstrip('/')}" if path else f"{upstream_base}/"
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            upstream = await client.get(
                upstream_url,
                params=request.query_params,
                headers={
                    "accept": request.headers.get("accept", "*/*"),
                    "user-agent": request.headers.get("user-agent", "FIT-TaskCenter-Proxy"),
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"flower proxy unavailable: {exc}") from exc

    excluded_headers = {"content-length", "transfer-encoding", "connection", "content-encoding"}
    response_headers: dict[str, Any] = {
        key: value for key, value in upstream.headers.items() if key.lower() not in excluded_headers
    }
    media_type = upstream.headers.get("content-type")

    if media_type and "text/html" in media_type:
        try:
            content = upstream.text
        except UnicodeDecodeError:
            content = upstream.content.decode("utf-8", errors="ignore")
        return HTMLResponse(
            content=_rewrite_flower_html(content),
            status_code=upstream.status_code,
            headers=response_headers,
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=media_type,
    )


@router.get("", response_model=ApiResponse[list[ScheduledTaskResponse]])
def list_tasks(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = TaskService(db)
    items = service.list_tasks(current_user.id)
    return ApiResponse(data=[ScheduledTaskResponse.model_validate(item) for item in items])


@router.get("/strategies", response_model=ApiResponse[list[RootVisibleStrategyResponse]])
def list_root_visible_strategies(
    keyword: str = Query(default="", min_length=0, max_length=128),
    user_id: int | None = Query(default=None, ge=1),
    username: str | None = Query(default=None, min_length=0, max_length=64),
    strategy_type: str = Query(default="stock", min_length=1, max_length=32),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_user),
):
    service = TaskService(db)
    items = service.list_root_visible_strategies(
        keyword=keyword,
        user_id=user_id,
        username=username,
        strategy_type=strategy_type,
    )
    return ApiResponse(data=[RootVisibleStrategyResponse.model_validate(item) for item in items])


@router.get("/{task_id}", response_model=ApiResponse[ScheduledTaskResponse])
def get_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = TaskService(db)
    try:
        item = service.get_task(task_id, current_user.id)
    except Exception as exc:  # noqa: BLE001
        _handle_task_exception(exc)
    return ApiResponse(data=ScheduledTaskResponse.model_validate(item))


@router.post("", response_model=ApiResponse[ScheduledTaskResponse])
def create_task(
    payload: TaskCreatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = TaskService(db)
    try:
        item = service.create_task(payload.model_dump(), current_user)
    except Exception as exc:  # noqa: BLE001
        _handle_task_exception(exc)
    return ApiResponse(data=ScheduledTaskResponse.model_validate(item))


@router.put("/{task_id}", response_model=ApiResponse[ScheduledTaskResponse])
def update_task(
    task_id: int,
    payload: TaskUpdatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = TaskService(db)
    try:
        item = service.update_task(task_id, payload.model_dump(), current_user)
    except Exception as exc:  # noqa: BLE001
        _handle_task_exception(exc)
    return ApiResponse(data=ScheduledTaskResponse.model_validate(item))


@router.delete("/{task_id}", response_model=ApiResponse[dict])
def delete_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = TaskService(db)
    try:
        service.delete_task(task_id, current_user.id)
    except Exception as exc:  # noqa: BLE001
        _handle_task_exception(exc)
    return ApiResponse(data={"id": task_id, "status": "deleted"})


@router.post("/{task_id}/toggle", response_model=ApiResponse[ScheduledTaskResponse])
def toggle_task(
    task_id: int,
    payload: TaskTogglePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = TaskService(db)
    try:
        item = service.toggle_task(task_id, payload.enabled, current_user)
    except Exception as exc:  # noqa: BLE001
        _handle_task_exception(exc)
    return ApiResponse(data=ScheduledTaskResponse.model_validate(item))


@router.post("/{task_id}/run", response_model=ApiResponse[ScheduledTaskRunResponse])
def run_task_now(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = TaskService(db)
    try:
        item = service.create_manual_run(task_id, current_user.id)
        async_result = execute_scheduled_task_run.delay(item["id"])
        item = service.bind_run_celery_task_id(item["id"], async_result.id)
    except Exception as exc:  # noqa: BLE001
        _handle_task_exception(exc)
    return ApiResponse(data=ScheduledTaskRunResponse.model_validate(item))


@router.get("/{task_id}/runs", response_model=ApiResponse[list[ScheduledTaskRunResponse]])
def list_task_runs(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = TaskService(db)
    try:
        items = service.list_runs(task_id, current_user.id)
    except Exception as exc:  # noqa: BLE001
        _handle_task_exception(exc)
    return ApiResponse(data=[ScheduledTaskRunResponse.model_validate(item) for item in items])


@router.get("/monitor/flower", response_class=Response)
async def proxy_flower_root(request: Request, _: User = Depends(require_root_user)):
    return await _proxy_flower("", request)


@router.get("/monitor/flower/{path:path}", response_class=Response)
async def proxy_flower_path(path: str, request: Request, _: User = Depends(require_root_user)):
    return await _proxy_flower(path, request)
