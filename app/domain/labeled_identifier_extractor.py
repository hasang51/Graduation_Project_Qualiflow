"""Conservative extraction of explicitly labeled traceability identifiers from text."""

from __future__ import annotations

import re
from typing import Any

from app.domain.field_mapping_registry import normalize_header, resolve_canonical_field

LABELED_TRACEABILITY_FIELDS: tuple[str, ...] = (
    "heat_number",
    "batch_number",
    "lot_number",
    "colata_number",
    "cast_number",
    "charge_number",
)

LABELED_IDENTIFIER_CONFIDENCE = 0.70

_LABEL_PATTERN = re.compile(
    r"\b("
    r"CAST\s*NO\.?|HEAT\s*NO\.?|BATCH\s*NO\.?|LOT\s*NO\.?|"
    r"COLATA\s*NO\.?|CHARGE\s*NO\.?"
    r")\s*[:#.\-]?\s*([A-Za-z0-9][A-Za-z0-9\-]*)",
    re.IGNORECASE,
)

_TRACEABILITY_FIELD_SET = frozenset(LABELED_TRACEABILITY_FIELDS)


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _field_empty(payload: dict[str, Any], field_name: str) -> bool:
    return not _text(payload.get(field_name))


def _has_conflicting_higher_priority(
    payload: dict[str, Any],
    field_name: str,
    value: str,
) -> bool:
    if field_name not in _TRACEABILITY_FIELD_SET:
        return True
    priority_index = LABELED_TRACEABILITY_FIELDS.index(field_name)
    for higher_field in LABELED_TRACEABILITY_FIELDS[:priority_index]:
        existing = _text(payload.get(higher_field))
        if existing and existing != value:
            return True
    return False


def extract_labeled_identifiers_from_text(text: str) -> list[tuple[str, str, str]]:
    """Return ``(canonical_field, raw_label, value)`` tuples found in ``text``."""

    matches: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in _LABEL_PATTERN.finditer(text or ""):
        raw_label = match.group(1).strip()
        value = match.group(2).strip()
        if not value:
            continue
        canonical = resolve_canonical_field(normalize_header(raw_label))
        if canonical not in _TRACEABILITY_FIELD_SET:
            continue
        key = (canonical, value)
        if key in seen:
            continue
        seen.add(key)
        matches.append((canonical, raw_label, value))
    return matches


def _ensure_field_confidence(payload: dict[str, Any]) -> dict[str, float]:
    existing = payload.get("field_confidence")
    if isinstance(existing, dict):
        return {str(key): float(value) for key, value in existing.items() if isinstance(value, (int, float))}
    return {}


def _apply_match(
    payload: dict[str, Any],
    *,
    canonical_field: str,
    raw_label: str,
    value: str,
) -> bool:
    if not _field_empty(payload, canonical_field):
        return False
    if _has_conflicting_higher_priority(payload, canonical_field, value):
        return False

    payload[canonical_field] = value
    field_confidence = _ensure_field_confidence(payload)
    field_confidence[canonical_field] = LABELED_IDENTIFIER_CONFIDENCE
    payload["field_confidence"] = field_confidence
    payload.setdefault("traceability_identifier_label", raw_label.upper())
    payload.setdefault("traceability_identifier_type", canonical_field)
    payload.setdefault("traceability_identifier_value", value)
    return True


def _iter_row_text_fields(row: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for key in ("item_id", "grade", "weight_or_length", "ai_analysis_remarks"):
        value = _text(row.get(key))
        if value:
            texts.append(value)
    return texts


def apply_labeled_identifiers(
    metadata: dict[str, Any],
    rows: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Apply labeled identifier extraction to metadata and rows.

    Returns ``(tokens, traces)`` for finalization auditing.
    """

    tokens: list[str] = []
    traces: list[dict[str, Any]] = []

    metadata_sources: list[tuple[str, dict[str, Any], str]] = []
    remarks = _text(metadata.get("ai_analysis_remarks"))
    if remarks:
        metadata_sources.append(("ai_analysis_remarks", metadata, remarks))
    product_description = _text(metadata.get("product_description"))
    if product_description:
        metadata_sources.append(("product_description", metadata, product_description))

    for source_name, payload, text in metadata_sources:
        for canonical_field, raw_label, value in extract_labeled_identifiers_from_text(text):
            if _apply_match(payload, canonical_field=canonical_field, raw_label=raw_label, value=value):
                tokens.append(f"{canonical_field}:from_labeled_text:{normalize_header(raw_label)}")
                traces.append(
                    {
                        "step": "labeled_identifier",
                        "scope": "metadata",
                        "source": source_name,
                        "field": canonical_field,
                        "label": raw_label,
                        "value": value,
                        "confidence": LABELED_IDENTIFIER_CONFIDENCE,
                    }
                )

    for row_index, row in enumerate(rows):
        combined = " ".join(_iter_row_text_fields(row))
        if not combined.strip():
            continue
        for canonical_field, raw_label, value in extract_labeled_identifiers_from_text(combined):
            if _apply_match(row, canonical_field=canonical_field, raw_label=raw_label, value=value):
                tokens.append(f"{canonical_field}:from_labeled_text:{normalize_header(raw_label)}")
                traces.append(
                    {
                        "step": "labeled_identifier",
                        "scope": "row",
                        "row_index": row_index,
                        "field": canonical_field,
                        "label": raw_label,
                        "value": value,
                        "confidence": LABELED_IDENTIFIER_CONFIDENCE,
                    }
                )

    return tokens, traces


__all__ = [
    "LABELED_IDENTIFIER_CONFIDENCE",
    "LABELED_TRACEABILITY_FIELDS",
    "apply_labeled_identifiers",
    "extract_labeled_identifiers_from_text",
]
