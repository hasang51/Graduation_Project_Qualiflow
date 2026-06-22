"""Backward-compatible database shim."""

from __future__ import annotations

from db.session import Base, SessionLocal, engine, get_db

__all__ = ["Base", "SessionLocal", "engine", "get_db"]
