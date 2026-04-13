from fastapi import APIRouter, Depends

from app.api.deps.auth import require_authenticated_user
from app.api.routes_auth import router as auth_router
from app.api.routes_notifications import router as notifications_router
from app.api.routes_progress import router as progress_router
from app.api.routes_stock import router as stock_router
from app.api.routes_tasks import router as tasks_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(
    notifications_router,
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_authenticated_user)],
)
api_router.include_router(
    stock_router,
    prefix="/stocks",
    tags=["stocks"],
    dependencies=[Depends(require_authenticated_user)],
)
api_router.include_router(
    progress_router,
    prefix="/progress",
    tags=["progress"],
    dependencies=[Depends(require_authenticated_user)],
)
api_router.include_router(
    tasks_router,
    prefix="/tasks",
    tags=["tasks"],
    dependencies=[Depends(require_authenticated_user)],
)
