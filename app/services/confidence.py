from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.extraction import ExtractedItem, UniversalDocumentExtraction
from app.domain.validation_config import get_validation_config
from app.services.extraction_finalizer import qualifies_for_confidence_exempt_auto_accept

CRITICAL_IDENTIFIER_CONFIDENCE_CAP = 0.70
LOW_CRITICAL_IDENTIFIER_CONFIDENCE_THRESHOLD = 0.80

# Substrings Stage B extraction_audit uses to report that a PDF column exists.
_ITEM_ID_ABSENT_HINTS = (
    "no item id",
    "no item-id",
    "no item identifier",
    "no separate item id",
    "no item id column",
    "without item id",
    "item id absent",
    "missing item id column",
    "no column for item id",
)

_HEAT_ABSENT_HINTS = (
    "no heat",
    "no heat no",
    "no heat number",
    "no heat column",
    "heat absent",
)


def extraction_audit_excuses_missing_field(
    audit: Any,
    *,
    field: str,
    items: list[ExtractedItem],
) -> bool:
    """If Stage B says a column does not appear in the raster, skip missing penalties.

    Only applies when *no* extracted row hallucinated a non-empty value for that
    field (document-level semantics).
    """

    if not audit or not isinstance(audit, str) or not audit.strip():
        return False
    low = audit.lower()
    field = field.lower()
    if field == "item_id":
        if any(getattr(it, "item_id", None) for it in items):
            return False
        return any(h in low for h in _ITEM_ID_ABSENT_HINTS)
    if field == "heat_number":
        if any(getattr(it, "heat_number", None) for it in items):
            return False
        return any(h in low for h in _HEAT_ABSENT_HINTS)
    return False


# When final confidence survives caps, preprocessing blur/noise is diagnostic only —
# never force human review purely on raster quality signals.
_DIAGNOSTIC_REVIEW_REASONS_ABOVE_CONFIDENCE_FLOOR = frozenset({"blurry/noisy document"})


@dataclass
class ConfidenceAssessment:
    final_confidence: float
    review_reasons: list[str]
    status: str
    metrics: dict[str, Any]


def _clamp(value: float, lower: float = 0.05, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _avg_page_metric(preprocessing_meta: dict[str, Any], key: str) -> float | None:
    pages = preprocessing_meta.get("pages", [])
    values = [float(page[key]) for page in pages if isinstance(page, dict) and key in page]
    if not values:
        return None
    return sum(values) / len(values)


def _table_found(preprocessing_meta: dict[str, Any]) -> bool:
    pages = preprocessing_meta.get("pages", [])
    return any(
        isinstance(page, dict)
        and isinstance(page.get("table_detection"), dict)
        and bool(page["table_detection"].get("table_found"))
        for page in pages
    )


def _missing_critical_fields_rate(
    items: list[ExtractedItem],
    config,
    *,
    preprocessing_meta: dict[str, Any] | None = None,
) -> float:
    if not items:
        return 1.0

    audit = (preprocessing_meta or {}).get("stage_b_extraction_audit")

    missing = 0
    total = 0
    for item in items:
        # Check basic string fields
        for field, value in [("item_id", item.item_id), ("heat_number", item.heat_number), ("grade", item.grade)]:
            if field not in config.mandatory_fields:
                continue
            if extraction_audit_excuses_missing_field(audit, field=field, items=items):
                continue
            total += 1
            if not value:
                missing += 1

        if item.mechanical_properties is not None:
            # Check mechanical properties
            for field, value in [
                ("yield_strength_mpa", item.mechanical_properties.yield_strength_mpa),
                ("tensile_strength_mpa", item.mechanical_properties.tensile_strength_mpa),
                ("elongation_percentage", item.mechanical_properties.elongation_percentage),
            ]:
                if field in config.mandatory_fields and field not in config.optional_fields:
                    total += 1
                    if value is None:
                        missing += 1

    return missing / max(total, 1)


def _suspicious_numeric_count(items: list[ExtractedItem]) -> int:
    count = 0
    for item in items:
        deviations = item.validation.deviations if item.validation else []
        count += sum(1 for deviation in deviations if "looks suspicious" in deviation.lower())
    return count


def _unresolved_row_count(items: list[ExtractedItem]) -> int:
    """Rows whose validation outcome is unresolved (None ``is_compliant``)."""

    count = 0
    for item in items:
        if item.validation is None:
            continue
        if item.validation.is_compliant is None and (item.validation.outcome or "").upper() != "NOT_APPLICABLE":
            count += 1
    return count


def _identifier_guard_events(preprocessing_meta: dict[str, Any]) -> list[dict[str, Any]]:
    guard = preprocessing_meta.get("identifier_guard")
    if not isinstance(guard, dict):
        return []

    events: list[dict[str, Any]] = []
    for bucket in guard.get("events") or []:
        if not isinstance(bucket, dict):
            continue
        suppressed = bucket.get("suppressed_identifiers")
        if isinstance(suppressed, list):
            events.extend(event for event in suppressed if isinstance(event, dict))
        elif bucket.get("field"):
            events.append(bucket)
    return events


def _has_low_critical_identifier_confidence(preprocessing_meta: dict[str, Any]) -> bool:
    for event in _identifier_guard_events(preprocessing_meta):
        confidence = event.get("confidence")
        if isinstance(confidence, (float, int)) and not isinstance(confidence, bool):
            if float(confidence) < LOW_CRITICAL_IDENTIFIER_CONFIDENCE_THRESHOLD:
                return True
        if event.get("reason") in {"low_identifier_confidence", "missing_identifier_confidence"}:
            return True
    return False


def _has_ambiguous_null_critical_identifier(preprocessing_meta: dict[str, Any]) -> bool:
    for event in _identifier_guard_events(preprocessing_meta):
        if event.get("accepted_value") is not None:
            continue
        reason = str(event.get("reason") or "").lower()
        evidence_note = str(event.get("evidence_note") or "").lower()
        if "ambig" in reason or "ambig" in evidence_note or reason == "visual_ambiguity":
            return True
    return False


def _normalization_penalty(review_reasons: list[str]) -> float:
    penalty = 0.0
    for reason in review_reasons:
        if reason.startswith("numeric_uncertain:"):
            penalty += 0.1
        elif reason.startswith("numeric_promoted_thousands:"):
            penalty += 0.05
        elif reason.startswith("header_row_conflict:"):
            penalty += 0.08
    return min(0.45, penalty)


def _classify_noise(avg_noise: float | None) -> str:
    if avg_noise is None:
        return "unknown"
    if avg_noise >= 25:
        return "severe"
    if avg_noise >= 14:
        return "moderate"
    return "low"


def _is_document_understood(extraction: UniversalDocumentExtraction) -> bool:
    return extraction.document_type != "Unknown document" or extraction.supplier_name != "Unknown supplier"


def normalize_confidence(
    extraction: UniversalDocumentExtraction,
    preprocessing_meta: dict[str, Any],
    raw_reported_total_items: int,
    review_confidence_threshold: float,
) -> ConfidenceAssessment:
    raw_confidence = extraction.raw_model_confidence or extraction.confidence_score
    items_len = len(extraction.items)
    table_found = _table_found(preprocessing_meta)
    avg_blur = _avg_page_metric(preprocessing_meta, "blur_score")
    avg_noise = _avg_page_metric(preprocessing_meta, "noise_estimate")

    config = get_validation_config(extraction.product_category)
    finalization_meta = (preprocessing_meta or {}).get("extraction_finalization")
    if isinstance(finalization_meta, dict) and finalization_meta.get("missing_critical_fields_rate") is not None:
        missing_rate = float(finalization_meta["missing_critical_fields_rate"])
    else:
        missing_rate = _missing_critical_fields_rate(
            extraction.items, config, preprocessing_meta=preprocessing_meta
        )
    suspicious_numeric = _suspicious_numeric_count(extraction.items)
    row_count_inconsistent = raw_reported_total_items != items_len
    document_understood = _is_document_understood(extraction)
    noise_severity = _classify_noise(avg_noise)
    low_identifier_confidence = _has_low_critical_identifier_confidence(preprocessing_meta)
    ambiguous_null_identifier = _has_ambiguous_null_critical_identifier(preprocessing_meta)

    adjusted = raw_confidence
    caps = [1.0]
    review_reasons = list(extraction.review_reasons)

    if items_len == 0:
        adjusted -= 0.18

    if avg_blur is not None:
        if avg_blur < 30:
            adjusted -= 0.15
            caps.append(0.50)
            review_reasons.append("blurry/noisy document")
        elif avg_blur < 80:
            adjusted -= 0.08
            caps.append(0.70)
        elif avg_blur < 150:
            adjusted -= 0.04 if missing_rate < 0.4 else 0.08
            if missing_rate >= 0.4:
                caps.append(0.7)

    if avg_noise is not None:
        if avg_noise >= 25:
            adjusted -= 0.12
            caps.append(0.55)
            review_reasons.append("blurry/noisy document")
        elif avg_noise >= 14:
            adjusted -= 0.06
            caps.append(0.75)

    if table_found and raw_reported_total_items == 0:
        caps.append(0.32)
        review_reasons.append("table exists but rows not extracted")

    if row_count_inconsistent:
        adjusted -= 0.10
        caps.append(0.5)
        review_reasons.append("row_count_inconsistent")

    if low_identifier_confidence:
        caps.append(CRITICAL_IDENTIFIER_CONFIDENCE_CAP)
        review_reasons.append("critical identifier confidence is low")

    if ambiguous_null_identifier:
        review_reasons.append("critical_identifier_unverified")
        review_reasons.append("traceability_unverified")

    if missing_rate >= 0.8:
        adjusted -= 0.12
        caps.append(0.50)
        review_reasons.append("many critical fields are missing")
    elif missing_rate >= 0.5:
        adjusted -= 0.06
        caps.append(0.70)

    if suspicious_numeric > 0:
        adjusted -= min(0.24, suspicious_numeric * 0.07)
        caps.append(0.45)
        review_reasons.append("suspicious numeric values")

    unresolved_rows = _unresolved_row_count(extraction.items)
    if unresolved_rows > 0:
        # Soft nudge only - unresolved grades / specs mean we *could not
        # validate*, not that the document is wrong. We neither hard-cap nor
        # push confidence below the review threshold on their own.
        adjusted -= min(0.08, unresolved_rows * 0.03)
        review_reasons.append("unresolved grade or spec")

    if document_understood and items_len == 0:
        caps.append(0.35)
        review_reasons.append("document understood but item extraction weak")

    final_confidence = _clamp(min(adjusted, min(caps)))
    confidence_exempt = qualifies_for_confidence_exempt_auto_accept(extraction)
    if final_confidence < review_confidence_threshold and not confidence_exempt:
        review_reasons.append("confidence falls below threshold")
    unique_reasons = sorted(set(review_reasons))
    high_floor = max(0.90, review_confidence_threshold)
    if final_confidence >= high_floor:
        unique_reasons = sorted(
            reason
            for reason in unique_reasons
            if reason not in _DIAGNOSTIC_REVIEW_REASONS_ABOVE_CONFIDENCE_FLOOR
        )
    if confidence_exempt:
        unique_reasons = sorted(
            reason for reason in unique_reasons if reason != "confidence falls below threshold"
        )
    status = "NEEDS_REVIEW" if unique_reasons else "COMPLETED"

    metrics = {
        "raw_model_confidence": raw_confidence,
        "final_confidence": final_confidence,
        "table_found": table_found,
        "avg_blur_score": avg_blur,
        "avg_noise_estimate": avg_noise,
        "noise_severity": noise_severity,
        "items_array_length": items_len,
        "raw_reported_total_items": raw_reported_total_items,
        "missing_critical_fields_rate": missing_rate,
        "suspicious_numeric_count": suspicious_numeric,
        "row_count_inconsistent": row_count_inconsistent,
        "document_understood": document_understood,
        "low_critical_identifier_confidence": low_identifier_confidence,
        "ambiguous_null_critical_identifier": ambiguous_null_identifier,
        "confidence_breakdown": {
            "extraction_confidence": round(_clamp(raw_confidence), 4),
            "normalization_confidence": round(_clamp(1.0 - _normalization_penalty(review_reasons)), 4),
            "spec_resolution_confidence": round(
                _clamp(1.0 - (unresolved_rows / max(len(extraction.items), 1))), 4
            ),
            "validation_confidence": round(
                _clamp(1.0 - (suspicious_numeric / max(len(extraction.items), 1) * 0.25)), 4
            ),
            "overall_decision_confidence": round(final_confidence, 4),
        },
    }

    return ConfidenceAssessment(
        final_confidence=final_confidence,
        review_reasons=unique_reasons,
        status=status,
        metrics=metrics,
    )
