from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    import anthropic


@lru_cache
def get_anthropic_client() -> "anthropic.Anthropic":
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required.")
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def reset_anthropic_client_cache() -> None:
    get_anthropic_client.cache_clear()
