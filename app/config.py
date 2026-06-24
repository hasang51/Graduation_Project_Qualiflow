"""Backward-compatible settings shim."""

from __future__ import annotations

from config.settings import Settings, get_settings

settings = get_settings()

__all__ = ["Settings", "get_settings", "settings"]
