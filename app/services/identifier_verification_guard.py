"""Apply OCR-aware verification to critical traceability identifiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.identifier_verification import (
    CRITICAL_TRACEABILITY_FIELDS,
    IDENTIFIER_CONFLICT_REASON,
    IDENTIFIER_OCR_USER_MESSAGE,
    OCR_UNCERTAIN_REASON,
    IdentifierCandidate,
    IdentifierVerificationAssessment,
    assess_identifier_field,
)
from app.schemas.extraction import ExtractedItem, UniversalDocumentExtraction


@dataclass
class IdentifierVerificationGuardResult:
    tokens: list[str] = field(default_factory=list)
    assessments: list[dict[str, Any]] = field(default_factory=list)
    flagged_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tokens": list(self.tokens),
            "assessments": list(self.assessments),
            "flagged_fields": list(self.flagged_fields),
        }


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _append_candidate(
    raw_candidates: dict[str, Any],
    *,
    field: str,
    value: str,
    source: str,
    reason: str,
) -> None:
    if not value:
        return
    entry = {
        "value": value,
        "source": source,
        "reason": reason,
        "accepted": False,
    }
    existing = raw_candidates.get(field)
    if existing is None:
        raw_candidates[field] = [entry]
        return
    if isinstance(existing, list):
        if any(_text(item.get("value") if isinstance(item, dict) else item) == value for item in existing):
            return
        existing.append(entry)
        return
    raw_candidates[field] = [existing, entry]


def _merge_assessment_into_target(
    target: ExtractedItem | UniversalDocumentExtraction,
    assessment: IdentifierVerificationAssessment,
    *,
    scope: str,
    row_index: int | None,
    tokens: list[str],
    flagged_fields: list[str],
) -> None:
    if not assessment.ocr_uncertain and not assessment.conflict:
        return

    target.needs_review = True
    target.identifier_visibility_verified = False
    raw_candidates = target.raw_identifier_candidates
    if not isinstance(raw_candidates, dict):
        raw_candidates = {}
        target.raw_identifier_candidates = raw_candidates

    for candidate in assessment.candidates:
        if candidate.source == "accepted":
            continue
        reason = (
            IDENTIFIER_CONFLICT_REASON
            if assessment.conflict
            else OCR_UNCERTAIN_REASON
        )
        _append_candidate(
            raw_candidates,
            field=assessment.field,
            value=candidate.value,
            source=candidate.source,
            reason=reason,
        )

    if assessment.ocr_uncertain and OCR_UNCERTAIN_REASON not in tokens:
        tokens.append(OCR_UNCERTAIN_REASON)
    if assessment.conflict and IDENTIFIER_CONFLICT_REASON not in tokens:
        tokens.append(IDENTIFIER_CONFLICT_REASON)

    field_key = (
        f"{assessment.field}:row{row_index}"
        if scope == "row" and row_index is not None
        else assessment.field
    )
    if field_key not in flagged_fields:
        flagged_fields.append(field_key)

def apply_identifier_verification_guard(
    extraction: UniversalDocumentExtraction,
) -> IdentifierVerificationGuardResult:
    """Flag OCR-uncertain identifiers and single-character candidate conflicts."""

    tokens: list[str] = []
    assessments: list[dict[str, Any]] = []
    flagged_fields: list[str] = []

    for field_name in CRITICAL_TRACEABILITY_FIELDS:
        accepted_value = getattr(extraction, field_name, None)
        if not _text(accepted_value):
            continue
        assessment = assess_identifier_field(
            field=field_name,
            accepted_value=accepted_value,
            raw_identifier_candidates=extraction.raw_identifier_candidates,
        )
        assessments.append({**assessment.to_dict(), "scope": "document"})
        _merge_assessment_into_target(
            extraction,
            assessment,
            scope="document",
            row_index=None,
            tokens=tokens,
            flagged_fields=flagged_fields,
        )

    for row_index, item in enumerate(extraction.items):
        extra_candidates: list[IdentifierCandidate] = []
        trace_value = _text(item.traceability_identifier_value)
        if trace_value and item.traceability_identifier_type:
            extra_candidates.append(
                IdentifierCandidate(
                    field=str(item.traceability_identifier_type),
                    value=trace_value,
                    source="traceability_identifier_value",
                )
            )

        for field_name in CRITICAL_TRACEABILITY_FIELDS:
            accepted_value = getattr(item, field_name, None)
            if not _text(accepted_value):
                continue
            assessment = assess_identifier_field(
                field=field_name,
                accepted_value=accepted_value,
                raw_identifier_candidates=item.raw_identifier_candidates,
                extra_candidates=extra_candidates,
            )
            assessments.append(
                {**assessment.to_dict(), "scope": "row", "row_index": row_index}
            )
            _merge_assessment_into_target(
                item,
                assessment,
                scope="row",
                row_index=row_index,
                tokens=tokens,
                flagged_fields=flagged_fields,
            )

    if tokens:
        extraction.needs_review = True
        extraction.review_reasons = list(
            dict.fromkeys([*extraction.review_reasons, *tokens])
        )
        if extraction.identifier_visibility_verified is not False:
            extraction.identifier_visibility_verified = False
        remarks = _text(extraction.ai_analysis_remarks)
        if IDENTIFIER_OCR_USER_MESSAGE not in remarks:
            extraction.ai_analysis_remarks = (
                f"{remarks} {IDENTIFIER_OCR_USER_MESSAGE}".strip()
                if remarks
                else IDENTIFIER_OCR_USER_MESSAGE
            )

    return IdentifierVerificationGuardResult(
        tokens=tokens,
        assessments=assessments,
        flagged_fields=flagged_fields,
    )


__all__ = [
    "IdentifierVerificationGuardResult",
    "apply_identifier_verification_guard",
]
