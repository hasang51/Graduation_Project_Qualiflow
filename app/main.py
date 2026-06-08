from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import Base, engine
from app.routes.analyses import router as analyses_router
from app.routes.auth import router as auth_router
from app.routes.extraction import router as extraction_router
from app.routes.health import router as health_router
from app.services.storage import ensure_storage_dirs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="QualiFlow - Document Extraction API",
        version="6.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    ensure_storage_dirs()
    Base.metadata.create_all(bind=engine)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(extraction_router)
    app.include_router(analyses_router)
    return app


app = create_app()
