"""Shared outcome taxonomy for validator, review policy, and UI.

The key design constraint is conservative semantics:

- unresolved evidence never becomes ``NON_COMPLIANT``
- unsupported spec families route to review
- missing prerequisites stay ``NOT_VALIDATED``
"""

from __future__ import annotations

from typing import Literal

Outcome = Literal[
    "COMPLIANT",
    "NON_COMPLIANT",
    "NOT_VALIDATED",
    "NEEDS_REVIEW",
    "UNRESOLVED_SPEC",
    "UNSUPPORTED_SPEC_FAMILY",
    "UNSUPPORTED_DOCUMENT",
    "EXPLICIT_UNMAPPED_GRADE",
    "MISSING_CRITICAL_FIELD_GRADE",
]

COMPLIANT: Outcome = "COMPLIANT"
NON_COMPLIANT: Outcome = "NON_COMPLIANT"
NOT_VALIDATED: Outcome = "NOT_VALIDATED"
NEEDS_REVIEW: Outcome = "NEEDS_REVIEW"
UNRESOLVED_SPEC: Outcome = "UNRESOLVED_SPEC"
UNSUPPORTED_SPEC_FAMILY: Outcome = "UNSUPPORTED_SPEC_FAMILY"
UNSUPPORTED_DOCUMENT: Outcome = "UNSUPPORTED_DOCUMENT"
EXPLICIT_UNMAPPED_GRADE: Outcome = "EXPLICIT_UNMAPPED_GRADE"
MISSING_CRITICAL_FIELD_GRADE: Outcome = "MISSING_CRITICAL_FIELD_GRADE"

REVIEW_OUTCOMES: set[Outcome] = {
    NEEDS_REVIEW,
    UNRESOLVED_SPEC,
    UNSUPPORTED_SPEC_FAMILY,
    UNSUPPORTED_DOCUMENT,
    EXPLICIT_UNMAPPED_GRADE,
    MISSING_CRITICAL_FIELD_GRADE,
}


def is_review_outcome(outcome: str | None) -> bool:
    if not outcome:
        return False
    return outcome.upper() in REVIEW_OUTCOMES


def aggregate_document_outcome(row_outcomes: list[str]) -> Outcome:
    """Derive a document-level outcome from canonical row outcomes."""

    normalized = [entry.upper() for entry in row_outcomes if entry]
    if not normalized:
        return NOT_VALIDATED
    if NON_COMPLIANT in normalized:
        return NON_COMPLIANT
    if any(entry in REVIEW_OUTCOMES for entry in normalized):
        return NEEDS_REVIEW
    if COMPLIANT in normalized and all(entry in {COMPLIANT, NOT_VALIDATED} for entry in normalized):
        return COMPLIANT
    return NOT_VALIDATED


__all__ = [
    "Outcome",
    "COMPLIANT",
    "NON_COMPLIANT",
    "NOT_VALIDATED",
    "NEEDS_REVIEW",
    "UNRESOLVED_SPEC",
    "UNSUPPORTED_SPEC_FAMILY",
    "UNSUPPORTED_DOCUMENT",
    "EXPLICIT_UNMAPPED_GRADE",
    "MISSING_CRITICAL_FIELD_GRADE",
    "REVIEW_OUTCOMES",
    "is_review_outcome",
    "aggregate_document_outcome",
]
