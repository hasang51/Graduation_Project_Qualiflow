from fastapi import APIRouter

from app.api.v1.routes import jobs_router, uploads_router

api_v1_router = APIRouter()
api_v1_router.include_router(uploads_router)
api_v1_router.include_router(jobs_router)

__all__ = ["api_v1_router"]
