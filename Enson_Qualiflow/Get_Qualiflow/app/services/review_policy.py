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
- Document quality is retained as diagnostic metadata, but it is not a
  standalone review gate.
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

from app.domain.outcome_taxonomy import (
    NEEDS_REVIEW,
    NON_COMPLIANT,
    UNSUPPORTED_SPEC_FAMILY,
    UNRESOLVED_SPEC,
)
from app.schemas.extraction import UniversalDocumentExtraction
from app.services.document_profiler import DocumentProfile

CRITICAL_STRING_FIELDS = ("heat_number", "grade")
CRITICAL_NUMERIC_FIELDS = ("yield_strength_mpa", "tensile_strength_mpa", "elongation_percentage")
REQUIRED_CRITICAL_FIELDS = (
    "heat_number",
    "grade",
    "yield_strength_mpa",
    "tensile_strength_mpa",
    "elongation_percentage",
)
SUPPORTED_DOCUMENT_TYPES = {
    "certificate of analysis",
    "coa",
    "mill test certificate",
    "mill test report",
    "material test certificate",
    "mtc",
    "inspection certificate",
    "test report",
    "test certificate",
    "certificate of quality",
    "certificate of conformity",
    "material certificate",
    "3.1 certificate",
    "en 10204",
}
TOKEN_FIELD_LABELS = {
    "yield_strength_mpa": "yield_strength",
    "tensile_strength_mpa": "tensile_strength",
    "heat_number": "heat_number",
    "grade": "grade",
    "elongation_percentage": "elongation",
}


@dataclass
class ReviewDecision:
    review_required: bool
    structured_reasons: list[str] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    evidence_gaps: list[str] = field(default_factory=list)
    reviewer_focus: list[str] = field(default_factory=list)
    all_reasons: list[str] = field(default_factory=list)
    decision: str | None = None
    confidence_summary: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        decision = self.decision or ("review_required" if self.review_required else "auto_accept")
        return {
            "decision": decision,
            "review_required": self.review_required,
            "needs_review": self.review_required,
            "structured_reasons": list(self.structured_reasons),
            "review_reasons": list(self.structured_reasons),
            "blocking_errors": list(self.blocking_reasons),
            "confidence_summary": dict(self.confidence_summary),
            "blocking_reasons": list(self.blocking_reasons),
            "evidence_gaps": list(self.evidence_gaps),
            "recommended_reviewer_focus": list(self.reviewer_focus),
            "all_reasons": list(self.all_reasons),
        }


def _normalise_token(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe_preserving_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _document_type_supported(value: Any) -> bool:
    normalised = _normalise_token(value)
    if not normalised or normalised == "unknown document":
        return False
    return any(known in normalised for known in SUPPORTED_DOCUMENT_TYPES)


def _profile_value(document_profile: Any, *keys: str) -> Any:
    if document_profile is None:
        return None
    if isinstance(document_profile, dict):
        for key in keys:
            if key in document_profile:
                return document_profile.get(key)
        return None
    for key in keys:
        if hasattr(document_profile, key):
            return getattr(document_profile, key)
    return None


def _quality_bucket(document_profile: Any) -> str:
    return _normalise_token(_profile_value(document_profile, "quality_bucket", "quality_class"))


def _extract_items_from_json(extracted_json: dict[str, Any]) -> list[dict[str, Any]]:
    items = extracted_json.get("items")
    return items if isinstance(items, list) else []


def _critical_value_present(extracted_json: dict[str, Any], field_name: str) -> bool:
    if not _is_missing(extracted_json.get(field_name)):
        return True

    items = _extract_items_from_json(extracted_json)
    if field_name in {"heat_number", "grade"}:
        return any(isinstance(item, dict) and not _is_missing(item.get(field_name)) for item in items)

    for item in items:
        if not isinstance(item, dict):
            continue
        mechanical = item.get("mechanical_properties")
        if isinstance(mechanical, dict) and not _is_missing(mechanical.get(field_name)):
            return True
        if not _is_missing(item.get(field_name)):
            return True
    return False


def _confidence_map(confidence: Any) -> dict[str, float]:
    """Extract field confidence values from common confidence payload shapes."""

    if confidence is None:
        return {}
    if isinstance(confidence, (float, int)):
        value = max(0.0, min(float(confidence), 1.0))
        return {"_overall": value}
    if not isinstance(confidence, dict):
        return {}

    for key in ("field_confidences", "fields", "critical_fields"):
        nested = confidence.get(key)
        if isinstance(nested, dict):
            return {
                str(field): max(0.0, min(float(value), 1.0))
                for field, value in nested.items()
                if _as_float(value) is not None
            }

    values: dict[str, float] = {}
    for field, value in confidence.items():
        parsed = _as_float(value)
        if parsed is not None:
            values[str(field)] = max(0.0, min(parsed, 1.0))
    return values


def _confidence_summary(
    extracted_json: dict[str, Any],
    confidence: Any,
) -> dict[str, float]:
    if isinstance(confidence, dict):
        min_value = _as_float(
            confidence.get("min_critical_field_confidence")
            if "min_critical_field_confidence" in confidence
            else confidence.get("min_critical_confidence")
        )
        avg_value = _as_float(confidence.get("avg_field_confidence"))
        if min_value is not None or avg_value is not None:
            safe_min = max(0.0, min(float(min_value if min_value is not None else 0.0), 1.0))
            safe_avg = max(0.0, min(float(avg_value if avg_value is not None else safe_min), 1.0))
            return {
                "min_critical_field_confidence": round(safe_min, 4),
                "avg_field_confidence": round(safe_avg, 4),
            }

    values = _confidence_map(confidence)
    if not values:
        row_confidences = [
            _as_float(item.get("row_confidence"))
            for item in _extract_items_from_json(extracted_json)
            if isinstance(item, dict)
        ]
        valid_rows = [value for value in row_confidences if value is not None]
        if valid_rows:
            values = {"_row_confidence": sum(valid_rows) / len(valid_rows)}
        else:
            overall = _as_float(extracted_json.get("confidence_score"))
            if overall is not None:
                values = {"_overall": max(0.0, min(overall, 1.0))}

    all_values = list(values.values())
    critical_values = [
        values[field]
        for field in REQUIRED_CRITICAL_FIELDS
        if field in values
    ]
    if not critical_values and "_overall" in values:
        critical_values = [values["_overall"]]
    if not critical_values and "_row_confidence" in values:
        critical_values = [values["_row_confidence"]]

    min_critical = min(critical_values) if critical_values else 0.0
    avg_field = (sum(all_values) / len(all_values)) if all_values else 0.0
    return {
        "min_critical_field_confidence": round(float(min_critical), 4),
        "avg_field_confidence": round(float(avg_field), 4),
    }


def _blocking_validation_errors(validation_errors: list[Any]) -> list[str]:
    blocking: list[str] = []
    for error in validation_errors or []:
        if isinstance(error, dict):
            tokens = [
                _normalise_token(error.get("severity")),
                _normalise_token(error.get("type")),
                _normalise_token(error.get("category")),
                _normalise_token(error.get("code")),
            ]
            is_blocking = bool(error.get("blocking")) or "blocking" in tokens or any(
                "blocking" in token for token in tokens
            )
            if is_blocking:
                blocking.append(str(error.get("code") or error.get("error") or error.get("message") or "blocking_error"))
        else:
            text = str(error)
            if "blocking" in _normalise_token(text):
                blocking.append(text)
    return _dedupe_preserving_order(blocking)


def evaluate_review_policy(
    *,
    extracted_json: dict[str, Any],
    confidence: Any,
    validation_errors: list[Any],
    document_profile: Any,
    confidence_threshold: float = 0.80,
) -> dict[str, Any]:
    """Apply the deterministic JSON review policy.

    The policy never mutates or auto-fills ``extracted_json``. Missing critical
    values remain missing and force ``review_required``.
    """

    review_reasons: list[str] = []
    blocking_errors = _blocking_validation_errors(validation_errors)
    summary = _confidence_summary(extracted_json, confidence)

    missing_fields = [
        field_name
        for field_name in REQUIRED_CRITICAL_FIELDS
        if not _critical_value_present(extracted_json, field_name)
    ]
    review_reasons.extend(f"missing_critical_field:{field}" for field in missing_fields)

    if blocking_errors:
        review_reasons.append("validation_blocking_error")

    if summary["min_critical_field_confidence"] < confidence_threshold:
        review_reasons.append("confidence_below_threshold")

    if not _document_type_supported(extracted_json.get("document_type")):
        review_reasons.append("unsupported_document_type")

    validation_passes = not validation_errors
    all_critical_exist = not missing_fields
    confidence_passes = summary["min_critical_field_confidence"] >= confidence_threshold
    supported_document = _document_type_supported(extracted_json.get("document_type"))

    if all_critical_exist and validation_passes and confidence_passes and supported_document and not review_reasons:
        decision = "auto_accept"
    else:
        decision = "review_required"

    return {
        "decision": decision,
        "review_reasons": _dedupe_preserving_order(review_reasons),
        "blocking_errors": blocking_errors,
        "confidence_summary": summary,
    }


apply_deterministic_review_policy = evaluate_review_policy


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
        if outcome == NEEDS_REVIEW:
            joined = " ".join(item.validation.deviations).lower()
            if "unknown grade" in joined:
                any_unknown_grade = True
            if "ambiguous grade" in joined:
                any_ambiguous = True
        elif outcome == "AMBIGUOUS_GRADE":
            any_ambiguous = True
        elif outcome == UNRESOLVED_SPEC:
            any_unresolved = True
        elif outcome == UNSUPPORTED_SPEC_FAMILY:
            tokens.append("unsupported_spec_family")
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

    # 1b. Unsupported document types can never be auto-accepted.
    if not _document_type_supported(extraction.document_type):
        structured.append("unsupported_document_type")

    # 2. Document quality is diagnostic metadata only. Concrete evidence such
    # as missing fields, low confidence, or row extraction failure gates review.

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
    blocking_reasons = [
        reason
        for reason in structured
        if reason
        in {
            "unresolved_spec",
            "unsupported_spec_family",
            "validation_conflict:row_non_compliant",
            "no_items_extracted",
        }
    ]
    evidence_gaps = [
        reason
        for reason in structured
        if reason.startswith("missing_critical_field:")
        or reason in {"confidence_below_threshold", "table_found_but_no_rows"}
        or reason.startswith("low_confidence:")
    ]
    reviewer_focus: list[str] = []
    if "unresolved_spec" in structured or "unsupported_spec_family" in structured:
        reviewer_focus.append("Confirm material family/spec source before compliance verdict.")
    if any(reason.startswith("missing_critical_field:") for reason in structured):
        reviewer_focus.append("Verify missing mechanical columns from original certificate.")
    if any(reason.startswith("header_row_conflict:") for reason in structured):
        reviewer_focus.append("Resolve header/row semantic conflicts and provenance.")
    if "validation_conflict:row_non_compliant" in structured:
        reviewer_focus.append("Re-check threshold violation evidence against resolved spec.")

    # Mutate in place so downstream callers see the enriched reasons.
    extraction.review_reasons = combined
    extraction.needs_review = needs_review
    if needs_review and extraction.status == "COMPLETED":
        extraction.status = "NEEDS_REVIEW"
    if extraction.outcome == NON_COMPLIANT and not needs_review:
        extraction.status = "COMPLETED"

    extracted_json = extraction.model_dump(mode="python")
    confidence_payload = dict(extraction.confidence_breakdown or {})
    confidence_payload.setdefault("_overall", extraction.confidence_score)
    deterministic = evaluate_review_policy(
        extracted_json=extracted_json,
        confidence=confidence_payload,
        validation_errors=[],
        document_profile=profile.to_dict() if profile is not None else None,
        confidence_threshold=review_confidence_threshold,
    )
    decision = deterministic["decision"] if not needs_review else "review_required"

    return ReviewDecision(
        review_required=needs_review,
        structured_reasons=structured,
        blocking_reasons=_dedupe_preserving_order(blocking_reasons),
        evidence_gaps=_dedupe_preserving_order(evidence_gaps),
        reviewer_focus=_dedupe_preserving_order(reviewer_focus),
        all_reasons=combined,
        decision=decision,
        confidence_summary=deterministic["confidence_summary"],
    )
