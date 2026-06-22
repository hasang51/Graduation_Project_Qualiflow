from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.settings import Settings


def test_production_rejects_insecure_jwt():
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(
            app_env="production",
            jwt_secret_key="change-me",
            cors_allow_origins="https://app.example.com",
            database_url="postgresql+psycopg2://user:pass@db:5432/qualiflow",
        )


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError, match="CORS_ALLOW_ORIGINS"):
        Settings(
            app_env="production",
            jwt_secret_key="x" * 32,
            cors_allow_origins="*",
            database_url="postgresql+psycopg2://user:pass@db:5432/qualiflow",
        )


def test_production_rejects_sqlite():
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(
            app_env="production",
            jwt_secret_key="x" * 32,
            cors_allow_origins="https://app.example.com",
            database_url="sqlite:///./data/qualiflow.db",
        )


def test_local_allows_sqlite_defaults():
    settings = Settings(app_env="local")
    assert settings.database_url.startswith("sqlite")
