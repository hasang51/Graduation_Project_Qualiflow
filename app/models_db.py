"""Backward-compatible ORM models shim."""

from __future__ import annotations

from db.models import AnalysisItem, AnalysisRun, Document, Job, User, utcnow

__all__ = ["AnalysisItem", "AnalysisRun", "Document", "Job", "User", "utcnow"]
