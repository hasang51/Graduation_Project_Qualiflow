from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("WORKER_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-with-32-characters-min")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("ANTHROPIC_MODEL", "")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("STORAGE_DIR", "./data/test_storage")

from config.settings import reset_settings_cache

reset_settings_cache()

from db.session import Base, SessionLocal, engine


@pytest.fixture(scope="session", autouse=True)
def _setup_db() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    reset_settings_cache()
    from app.services.storage.factory import reset_storage_backend_cache

    reset_storage_backend_cache()
    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def minimal_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
