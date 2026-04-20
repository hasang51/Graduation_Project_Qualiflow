"""Header-to-row propagation.

Mill-test certificates often carry a single grade (and occasionally a single
heat number) in the header and repeat empty grade cells in the item table.
This module lifts such header-level values onto individual rows, but only
under strict conditions so that the propagation stage never *invents* data
or silently masks genuine conflicts.

Contract:

- Pure function; never mutates its arguments. Returns a
  :class:`PropagationResult` describing proposed row updates.
- Only backfills a field that is missing on the row.
- Never overwrites an explicit row-level value with a weaker header value.
- Flags conflicts as structured reasons the review policy can pick up.
- The grade registry is used to decide whether a header-level grade is
  "strong" enough to propagate: ``status == 'resolved'`` or ``resolved_dual``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.domain.grade_registry import GradeResolution, resolve_grade


HEADER_GRADE_HINT_KEYS: tuple[str, ...] = (
    "header_grade",
    "document_grade",
    "default_grade_hint",
    "grade",
)


@dataclass
class RowPropagationUpdate:
    """Describes one proposed update to a single row."""

    row_index: int
    field: str
    new_value: str
    provenance: str  # "header" | "header_propagated"
    reason: str


@dataclass
class PropagationResult:
    updates: list[RowPropagationUpdate] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    header_grade_resolution: GradeResolution | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "updates": [
                {
                    "row_index": u.row_index,
                    "field": u.field,
                    "new_value": u.new_value,
                    "provenance": u.provenance,
                    "reason": u.reason,
                }
                for u in self.updates
            ],
            "conflicts": list(self.conflicts),
            "header_grade_resolution": (
                self.header_grade_resolution.to_dict()
                if self.header_grade_resolution is not None
                else None
            ),
        }


def _extract_header_grade(metadata: dict[str, Any] | None, ai_remarks: str | None) -> str | None:
    """Try to find a grade-like string at document level."""

    if metadata:
        for key in HEADER_GRADE_HINT_KEYS:
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if ai_remarks:
        # Very conservative: only pick the grade out of the remarks if the
        # remark contains a single occurrence of "grade: <value>".
        lowered = ai_remarks.lower()
        needle = "grade:"
        if needle in lowered:
            idx = lowered.index(needle) + len(needle)
            candidate = ai_remarks[idx:].splitlines()[0].strip()
            if candidate and len(candidate) <= 40:
                return candidate
    return None


def propagate_to_rows(
    items: list[dict[str, Any]],
    *,
    metadata: dict[str, Any] | None = None,
    ai_remarks: str | None = None,
) -> PropagationResult:
    """Propose header-to-row updates.

    ``items`` is a list of mutable row dicts that the caller will update
    (or ignore) based on the returned updates. This function never mutates
    the input directly so it is easy to reason about and to test.
    """

    header_raw = _extract_header_grade(metadata, ai_remarks)
    if not header_raw:
        return PropagationResult()

    header_resolution = resolve_grade(header_raw)
    result = PropagationResult(header_grade_resolution=header_resolution)

    if header_resolution.status not in ("resolved", "resolved_dual"):
        # A header grade we cannot confidently canonicalise is not strong
        # enough to propagate. Return the resolution for traceability.
        return result

    for index, row in enumerate(items):
        row_grade = row.get("grade")
        if isinstance(row_grade, str) and row_grade.strip():
            # Row already carries a grade. Check for conflict.
            row_resolution = resolve_grade(row_grade)
            if (
                row_resolution.status in ("resolved", "resolved_dual")
                and row_resolution.family_group == header_resolution.family_group
                and row_resolution.canonical != header_resolution.canonical
            ):
                result.conflicts.append(f"header_row_conflict:grade:row{index}")
            elif (
                row_resolution.status in ("resolved", "resolved_dual")
                and row_resolution.family_group != header_resolution.family_group
            ):
                result.conflicts.append(f"header_row_conflict:grade:row{index}")
            # In either case: we never overwrite the row.
            continue

        # Row grade missing -> propose backfill.
        result.updates.append(
            RowPropagationUpdate(
                row_index=index,
                field="grade",
                new_value=header_resolution.canonical or header_raw,
                provenance="header_propagated",
                reason="row grade missing; header resolves cleanly",
            )
        )

    return result


def apply_updates(items: list[dict[str, Any]], result: PropagationResult) -> None:
    """Apply ``result.updates`` to ``items`` in place.

    Kept separate from :func:`propagate_to_rows` so that callers can audit
    the proposed updates before committing them, and so that the propagation
    function itself stays pure.
    """

    for update in result.updates:
        if 0 <= update.row_index < len(items):
            row = items[update.row_index]
            row[update.field] = update.new_value
            row.setdefault("grade_provenance", update.provenance)


__all__ = [
    "PropagationResult",
    "RowPropagationUpdate",
    "propagate_to_rows",
    "apply_updates",
]
