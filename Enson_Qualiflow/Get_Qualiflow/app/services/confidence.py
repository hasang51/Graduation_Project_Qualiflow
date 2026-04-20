from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.extraction import ExtractedItem, UniversalDocumentExtraction


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


def _missing_critical_fields_rate(items: list[ExtractedItem]) -> float:
    if not items:
        return 1.0

    missing = 0
    total = 0
    for item in items:
        for value in (item.item_id, item.heat_number, item.grade):
            total += 1
            if not value:
                missing += 1

        if item.mechanical_properties is not None:
            for value in (
                item.mechanical_properties.yield_strength_mpa,
                item.mechanical_properties.tensile_strength_mpa,
                item.mechanical_properties.elongation_percentage,
            ):
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
    missing_rate = _missing_critical_fields_rate(extraction.items)
    suspicious_numeric = _suspicious_numeric_count(extraction.items)
    row_count_inconsistent = raw_reported_total_items != items_len
    document_understood = _is_document_understood(extraction)
    noise_severity = _classify_noise(avg_noise)

    adjusted = raw_confidence
    caps = [1.0]
    review_reasons = list(extraction.review_reasons)

    if items_len == 0:
        adjusted -= 0.18

    if avg_blur is not None:
        if avg_blur < 80:
            adjusted -= 0.18
            caps.append(0.45)
            review_reasons.append("blurry/noisy document")
        elif avg_blur < 150:
            adjusted -= 0.08
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
        review_reasons.append("row count mismatches")

    if missing_rate >= 0.7:
        adjusted -= 0.16
        caps.append(0.4)
        review_reasons.append("many critical fields are missing")
    elif missing_rate >= 0.4:
        adjusted -= 0.08
        caps.append(0.65)

    if suspicious_numeric > 0:
        adjusted -= min(0.24, suspicious_numeric * 0.07)
        caps.append(0.45)
        review_reasons.append("suspicious numeric values")

    if document_understood and items_len == 0:
        caps.append(0.35)
        review_reasons.append("document understood but item extraction weak")

    final_confidence = _clamp(min(adjusted, min(caps)))
    if final_confidence < review_confidence_threshold:
        review_reasons.append("confidence falls below threshold")
    unique_reasons = sorted(set(review_reasons))
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
    }

    return ConfidenceAssessment(
        final_confidence=final_confidence,
        review_reasons=unique_reasons,
        status=status,
        metrics=metrics,
    )
