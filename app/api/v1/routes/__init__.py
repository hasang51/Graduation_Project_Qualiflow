from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.jobs import router as jobs_router
from app.api.v1.routes.uploads import router as uploads_router

__all__ = ["health_router", "jobs_router", "uploads_router"]
