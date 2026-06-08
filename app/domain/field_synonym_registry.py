"""Canonical field synonym registry.

This module wraps the existing field mapping registry behind a semantic
interface used by the normalisation layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.field_mapping_registry import CANONICAL_FIELDS, normalize_header, resolve_canonical_field


@dataclass(frozen=True)
class FieldResolution:
    raw_field: str
    normalized_field: str
    canonical_field: str | None
    confidence: float
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "raw_field": self.raw_field,
            "normalized_field": self.normalized_field,
            "canonical_field": self.canonical_field,
            "confidence": self.confidence,
            "reason": self.reason,
        }


def resolve_field_name(raw_field: str | None) -> FieldResolution:
    text = (raw_field or "").strip()
    normalized = normalize_header(text) if text else ""
    canonical = resolve_canonical_field(text) if text else None
    if not text:
        return FieldResolution(
            raw_field="",
            normalized_field="",
            canonical_field=None,
            confidence=0.0,
            reason="empty field",
        )
    if canonical is not None:
        return FieldResolution(
            raw_field=text,
            normalized_field=normalized,
            canonical_field=canonical,
            confidence=1.0,
            reason="registry synonym match",
        )
    return FieldResolution(
        raw_field=text,
        normalized_field=normalized,
        canonical_field=None,
        confidence=0.0,
        reason="unresolved field alias",
    )


def canonical_field_names() -> list[str]:
    return sorted(CANONICAL_FIELDS.keys())


__all__ = ["FieldResolution", "resolve_field_name", "canonical_field_names"]
