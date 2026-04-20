"""Grade alias registry adapter for semantic normalisation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.grade_registry import GradeResolution, resolve_grade


@dataclass(frozen=True)
class GradeSemanticResolution:
    raw_grade: str
    normalized_grade: str
    tokens: tuple[str, ...]
    candidates: tuple[str, ...]
    status: str
    canonical: str | None
    confidence: float
    ambiguous: bool
    unresolved: bool
    reason: str
    family_group: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "raw_grade": self.raw_grade,
            "normalized_grade": self.normalized_grade,
            "tokens": list(self.tokens),
            "candidates": list(self.candidates),
            "status": self.status,
            "canonical": self.canonical,
            "confidence": self.confidence,
            "ambiguous": self.ambiguous,
            "unresolved": self.unresolved,
            "reason": self.reason,
            "family_group": self.family_group,
        }


def _tokenize(normalized_grade: str) -> tuple[str, ...]:
    if not normalized_grade:
        return ()
    return tuple(token for token in re.split(r"\s*[/,;]+\s*", normalized_grade) if token)


def resolve_grade_semantics(raw_grade: str | None) -> GradeSemanticResolution:
    grade = (raw_grade or "").strip()
    resolution: GradeResolution = resolve_grade(grade)
    tokens = _tokenize(resolution.normalized)
    unresolved = resolution.status in {"unknown", "empty", "ambiguous"}
    ambiguous = resolution.status == "ambiguous"
    return GradeSemanticResolution(
        raw_grade=grade,
        normalized_grade=resolution.normalized,
        tokens=tokens,
        candidates=resolution.candidates,
        status=resolution.status,
        canonical=resolution.canonical,
        confidence=resolution.confidence,
        ambiguous=ambiguous,
        unresolved=unresolved,
        reason=resolution.reason,
        family_group=resolution.family_group,
    )


__all__ = ["GradeSemanticResolution", "resolve_grade_semantics"]
