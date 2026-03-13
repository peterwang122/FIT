from fastapi import APIRouter

from app.api.routes_stock import router as stock_router

api_router = APIRouter()
api_router.include_router(stock_router, prefix="/stocks", tags=["stocks"])
