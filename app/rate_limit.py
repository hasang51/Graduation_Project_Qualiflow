from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings


def _limiter_key(request: Request) -> str:
    if request.url.path in {"/healthz", "/readyz", "/metrics", "/health"}:
        return "health"
    return get_remote_address(request)


limiter = Limiter(
    key_func=_limiter_key,
    enabled=settings.rate_limit_enabled,
    default_limits=[settings.rate_limit_default],
)
