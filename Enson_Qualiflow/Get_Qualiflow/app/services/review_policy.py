"""Deterministic review-gating policy.

:func:`apply_review_policy` is the single auditable place that decides whether
an extraction result needs human review. It runs after the validator and the
confidence normaliser and appends a set of *structured* review reason tokens
on top of whatever those components have already recorded.

Token conventions
-----------------
Tokens are ``key:value`` strings so downstream tooling can parse them
programmatically. All existing free-form reasons (from the validator /
confidence normaliser) are preserved for backward compatibility — the
structured tokens are *additive*.

Canonical tokens:

- ``missing_critical_field:<field>`` — a critical field is missing across all
  rows (``yield_strength``, ``tensile_strength``, ``heat_number``, ``grade``).
- ``document_quality:<quality_class>`` — document was classified as
  ``scan_degraded`` (or ``scan_clean`` + extra concerns).
- ``low_confidence:<field>`` — final confidence is low AND a specific critical
  numeric field is suspicious or missing.
- ``validation_conflict:<reason>`` — validator reported deviations
  (non-compliant rows, suspicious numbers, heat pattern inconsistencies).
- ``row_count_inconsistent`` — reported vs. extracted item count mismatch.
- ``no_items_extracted`` — zero items parsed.
- ``table_found_but_no_rows`` — table geometry detected but rows empty.
- ``confidence_below_threshold`` — final confidence < review threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.schemas.extraction import UniversalDocumentExtraction
from app.services.document_profiler import DocumentProfile

CRITICAL_STRING_FIELDS = ("heat_number", "grade")
CRITICAL_NUMERIC_FIELDS = ("yield_strength_mpa", "tensile_strength_mpa")
TOKEN_FIELD_LABELS = {
    "yield_strength_mpa": "yield_strength",
    "tensile_strength_mpa": "tensile_strength",
    "heat_number": "heat_number",
    "grade": "grade",
    "elongation_percentage": "elongation",
}


@dataclass
class ReviewDecision:
    needs_review: bool
    structured_reasons: list[str] = field(default_factory=list)
    all_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "needs_review": self.needs_review,
            "structured_reasons": list(self.structured_reasons),
            "all_reasons": list(self.all_reasons),
        }


def _missing_critical_fields(extraction: UniversalDocumentExtraction) -> list[str]:
    """Return tokens for critical fields that are missing across *all* rows."""

    if not extraction.items:
        # "No items" is handled separately; do not flag every field.
        return []

    missing_tokens: list[str] = []

    # String fields: missing on every row
    for field_name in CRITICAL_STRING_FIELDS:
        if all(not getattr(item, field_name, None) for item in extraction.items):
            label = TOKEN_FIELD_LABELS.get(field_name, field_name)
            missing_tokens.append(f"missing_critical_field:{label}")

    # Numeric fields: missing on every row
    for field_name in CRITICAL_NUMERIC_FIELDS:
        all_missing = True
        for item in extraction.items:
            mp = item.mechanical_properties
            if mp is not None and getattr(mp, field_name, None) is not None:
                all_missing = False
                break
        if all_missing:
            label = TOKEN_FIELD_LABELS.get(field_name, field_name)
            missing_tokens.append(f"missing_critical_field:{label}")

    return missing_tokens


def _validation_conflict_tokens(extraction: UniversalDocumentExtraction) -> list[str]:
    tokens: list[str] = []
    any_non_compliant = False
    any_unresolved = False
    any_ambiguous = False
    any_unknown_grade = False
    suspicious_seen = False
    heat_mismatch_seen = False
    separator_mismatch_seen = False
    grade_spec_mismatch_seen = False
    unit_missing_seen = False

    for item in extraction.items:
        if item.validation is None:
            continue
        # Tri-state: only flip ``any_non_compliant`` on an explicit False,
        # never on ``None`` (which means unresolved / not applicable).
        if item.validation.is_compliant is False:
            any_non_compliant = True
        outcome = (item.validation.outcome or "").upper()
        if outcome == "UNKNOWN_GRADE":
            any_unknown_grade = True
        elif outcome == "AMBIGUOUS_GRADE":
            any_ambiguous = True
        elif outcome == "UNRESOLVED_SPEC":
            any_unresolved = True
        for deviation in item.validation.deviations:
            lowered = deviation.lower()
            if "looks suspicious" in lowered:
                suspicious_seen = True
            if "heat number" in lowered and "inconsistent" in lowered:
                heat_mismatch_seen = True
            if "mixes separators" in lowered or "malformed" in lowered:
                separator_mismatch_seen = True
            if "inconsistent with the extracted mechanical values" in lowered:
                grade_spec_mismatch_seen = True
            if "lacks a clear unit" in lowered:
                unit_missing_seen = True

    if any_non_compliant:
        tokens.append("validation_conflict:row_non_compliant")
    if any_unknown_grade:
        tokens.append("unresolved_grade")
    if any_ambiguous:
        tokens.append("ambiguous_grade")
    if any_unresolved:
        tokens.append("unresolved_spec")
    if suspicious_seen:
        tokens.append("validation_conflict:suspicious_numeric_values")
    if heat_mismatch_seen:
        tokens.append("validation_conflict:heat_number_inconsistency")
    if separator_mismatch_seen:
        tokens.append("validation_conflict:malformed_numeric_strings")
    if grade_spec_mismatch_seen:
        tokens.append("validation_conflict:grade_spec_mismatch")
    if unit_missing_seen:
        tokens.append("validation_conflict:missing_unit")
    return tokens


def _numeric_parser_tokens(extraction: UniversalDocumentExtraction) -> list[str]:
    """Promote pipeline-level numeric-parser tokens to structured reasons."""

    tokens: list[str] = []
    for reason in extraction.review_reasons:
        if reason.startswith("numeric_uncertain:") or reason.startswith("numeric_promoted_thousands:"):
            tokens.append(reason)
        elif reason.startswith("unresolved_grade:"):
            tokens.append("unresolved_grade")
        elif reason.startswith("ambiguous_grade:"):
            tokens.append("ambiguous_grade")
        elif reason.startswith("unresolved_spec:"):
            tokens.append("unresolved_spec")
        elif reason.startswith("header_row_conflict:"):
            tokens.append("header_row_conflict:grade")
    return tokens


def _numeric_field_is_suspicious(extraction: UniversalDocumentExtraction, field_name: str) -> bool:
    needle_variants = {
        "yield_strength_mpa": "yield",
        "tensile_strength_mpa": "tensile",
        "elongation_percentage": "elongation",
    }
    needle = needle_variants.get(field_name, field_name)
    for item in extraction.items:
        if item.validation is None:
            continue
        for deviation in item.validation.deviations:
            lowered = deviation.lower()
            if "looks suspicious" in lowered and needle in lowered:
                return True
    return False


def _low_confidence_field_tokens(
    extraction: UniversalDocumentExtraction,
    profile: DocumentProfile | None,
    threshold: float,
) -> list[str]:
    """On degraded scans with low final confidence, flag specific critical fields."""

    tokens: list[str] = []
    final_confidence = extraction.confidence_score or 0.0
    if final_confidence >= threshold:
        return tokens
    if profile is not None and profile.quality_class != "scan_degraded":
        # Low-confidence-on-numeric tokens are only emitted when the document
        # itself is degraded. The generic ``confidence_below_threshold`` token
        # is emitted separately below.
        return tokens

    for field_name in CRITICAL_NUMERIC_FIELDS:
        suspicious_or_missing = _numeric_field_is_suspicious(extraction, field_name)
        if not suspicious_or_missing:
            # Check missing-everywhere as well
            all_missing = True
            for item in extraction.items:
                mp = item.mechanical_properties
                if mp is not None and getattr(mp, field_name, None) is not None:
                    all_missing = False
                    break
            suspicious_or_missing = all_missing and len(extraction.items) > 0

        if suspicious_or_missing:
            label = TOKEN_FIELD_LABELS.get(field_name, field_name)
            tokens.append(f"low_confidence:{label}")
    return tokens


def _dedupe_preserving_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def apply_review_policy(
    extraction: UniversalDocumentExtraction,
    *,
    profile: DocumentProfile | None = None,
    preprocessing_meta: dict[str, Any] | None = None,
    review_confidence_threshold: float = 0.75,
) -> ReviewDecision:
    """Compute the review decision and mutate ``extraction`` in place.

    The function appends structured tokens to ``extraction.review_reasons``
    without discarding existing reasons.
    """

    structured: list[str] = []
    final_confidence = extraction.confidence_score or 0.0

    # 1. Missing critical fields
    structured.extend(_missing_critical_fields(extraction))

    # 2. Document quality
    if profile is not None and profile.quality_class == "scan_degraded":
        structured.append("document_quality:scan_degraded")
    elif profile is not None and profile.quality_class == "scan_clean":
        # Only flag scan_clean when other evidence suggests the model struggled.
        if final_confidence < review_confidence_threshold or not extraction.items:
            structured.append("document_quality:scan_clean")

    # 3. Validation conflicts
    structured.extend(_validation_conflict_tokens(extraction))

    # 3b. Numeric-parser + header-propagation tokens surfaced from pipeline.
    structured.extend(_numeric_parser_tokens(extraction))

    # 4. Row count / item issues
    if not extraction.items:
        structured.append("no_items_extracted")
        if preprocessing_meta is not None:
            pages = preprocessing_meta.get("pages", [])
            if any(
                isinstance(page, dict)
                and isinstance(page.get("table_detection"), dict)
                and bool(page["table_detection"].get("table_found"))
                for page in pages
            ):
                structured.append("table_found_but_no_rows")

    if extraction.total_items_detected != len(extraction.items):
        structured.append("row_count_inconsistent")

    # 5. Field-level low confidence on degraded docs
    structured.extend(
        _low_confidence_field_tokens(extraction, profile, review_confidence_threshold)
    )

    # 6. Confidence below threshold (generic)
    if final_confidence < review_confidence_threshold:
        structured.append("confidence_below_threshold")

    structured = _dedupe_preserving_order(structured)

    combined = _dedupe_preserving_order([*extraction.review_reasons, *structured])
    needs_review = bool(structured) or bool(extraction.needs_review) or bool(combined)

    # Mutate in place so downstream callers see the enriched reasons.
    extraction.review_reasons = combined
    extraction.needs_review = needs_review
    if needs_review and extraction.status == "COMPLETED":
        extraction.status = "NEEDS_REVIEW"

    return ReviewDecision(
        needs_review=needs_review,
        structured_reasons=structured,
        all_reasons=combined,
    )
