from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


PROPERTY_LABELS: dict[str, tuple[str, ...]] = {
    "yield_strength_mpa": ("yield", "snervamento", "proof"),
    "tensile_strength_mpa": ("tensile", "carico di rottura", "rm"),
    "elongation_percentage": ("elongation", "allungamento", "a5"),
}
HEADER_HEAT_KEYS = ("heat_number", "header_heat_number", "cast_number")
HEADER_GRADE_KEYS = ("header_grade", "document_grade", "product_grade", "grade")
HEADER_WEIGHT_KEYS = ("weight_or_length", "product_weight", "quantity")


@dataclass
class RowShapeNormalizationResult:
    rows: list[dict[str, Any]]
    tokens: list[str] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _metadata_value(metadata: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _property_field(row: dict[str, Any]) -> str | None:
    label = f"{_text(row.get('item_id'))} {_text(row.get('grade'))}".lower()
    mechanical = row.get("mechanical_properties")
    if not isinstance(mechanical, dict):
        return None
    populated = [key for key, value in mechanical.items() if value is not None]
    if len(populated) == 1:
        return populated[0]
    for field_name, needles in PROPERTY_LABELS.items():
        if any(needle in label for needle in needles):
            return field_name
    return None


def _group_key(row: dict[str, Any]) -> str:
    grade = _text(row.get("grade"))
    if grade:
        return grade
    item_id = _text(row.get("item_id"))
    if "-" in item_id:
        return item_id.split("-", 1)[0].strip()
    return "default"


def _product_detail_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        item_id = _text(row.get("item_id")).lower()
        mechanical = row.get("mechanical_properties")
        if "product" in item_id and not isinstance(mechanical, dict):
            return row
    return None


def _confidence(values: list[Any]) -> float | None:
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    if not numbers:
        return None
    return max(0.05, min(1.0, sum(numbers) / len(numbers)))


def _has_complete_mechanicals(row: dict[str, Any]) -> bool:
    mechanical = row.get("mechanical_properties")
    if not isinstance(mechanical, dict):
        return False
    return all(
        mechanical.get(field) is not None
        for field in ("yield_strength_mpa", "tensile_strength_mpa", "elongation_percentage")
    )


def _looks_like_classification_id(value: Any) -> bool:
    text = _text(value).upper()
    return bool(re.fullmatch(r"[A-Z]\d{1,3}", text))


def _classification_label(row: dict[str, Any]) -> str | None:
    for key in ("item_id", "grade"):
        value = _text(row.get(key))
        if _looks_like_classification_id(value):
            return value
    return None


def _grade_hint(metadata: dict[str, Any]) -> str | None:
    explicit = _metadata_value(metadata, HEADER_GRADE_KEYS)
    if explicit:
        return explicit
    product = _text(metadata.get("product_description")).upper()
    if "SG2" in product:
        return "SG2"
    supplier = _text(metadata.get("supplier_name")).upper()
    # NOVOFIL welding-wire certificates can report M21/C1 shielding-gas
    # classifications as rows while the product grade is SG2.
    if "NOVOFIL" in supplier:
        return "SG2"
    return None


def collapse_vertical_mechanical_rows(
    rows: list[dict[str, Any]],
    *,
    metadata: dict[str, Any],
) -> RowShapeNormalizationResult:
    """Collapse property-per-row LLM output into item-centric rows.

    Some MTCs report mechanical values vertically: one line for yield, one for
    tensile, one for elongation. The API schema, however, expects one material
    item row containing all mechanical properties. This normalizer only acts on
    clear vertical-table signatures and otherwise returns rows unchanged.
    """

    property_rows: list[tuple[int, dict[str, Any], str]] = []
    for index, row in enumerate(rows):
        field_name = _property_field(row)
        if field_name is not None:
            property_rows.append((index, row, field_name))

    if len(property_rows) < 2:
        return RowShapeNormalizationResult(rows=rows)
    if any(_text(row.get("heat_number")) for _, row, _ in property_rows):
        return RowShapeNormalizationResult(rows=rows)

    grouped: dict[str, dict[str, Any]] = {}
    for _, row, field_name in property_rows:
        group = grouped.setdefault(
            _group_key(row),
            {
                "mechanical_properties": {
                    "yield_strength_mpa": None,
                    "tensile_strength_mpa": None,
                    "elongation_percentage": None,
                },
                "row_confidences": [],
                "source_rows": [],
            },
        )
        mechanical = row.get("mechanical_properties") or {}
        value = mechanical.get(field_name) if isinstance(mechanical, dict) else None
        if value is not None and group["mechanical_properties"][field_name] is None:
            group["mechanical_properties"][field_name] = value
        group["row_confidences"].append(row.get("row_confidence"))
        group["source_rows"].append(row.get("item_id"))

    complete_groups = [
        (group_name, payload)
        for group_name, payload in grouped.items()
        if all(value is not None for value in payload["mechanical_properties"].values())
    ]
    if not complete_groups:
        return RowShapeNormalizationResult(rows=rows)

    selected_group, payload = complete_groups[0]
    product_row = _product_detail_row(rows)
    heat_number = _metadata_value(metadata, HEADER_HEAT_KEYS)
    grade = _metadata_value(metadata, HEADER_GRADE_KEYS)
    weight = _metadata_value(metadata, HEADER_WEIGHT_KEYS)
    if product_row is not None:
        heat_number = heat_number or _text(product_row.get("heat_number")) or None
        grade = grade or _text(product_row.get("grade")) or None
        weight = weight or _text(product_row.get("weight_or_length")) or None

    collapsed = {
        "item_id": None,
        "heat_number": heat_number,
        "grade": grade,
        "weight_or_length": weight,
        "mechanical_properties": payload["mechanical_properties"],
        "row_confidence": _confidence(payload["row_confidences"]),
    }
    # item_id intentionally None: collapsed rows originate from vertically split
    # mechanical-property lines whose ``item_id`` cells are property labels —
    # not raster Item ID traceability columns.

    trace = {
        "strategy": "vertical_mechanical_table_collapse",
        "selected_group": selected_group,
        "source_rows": payload["source_rows"],
        "group_count": len(grouped),
        "product_detail_found": product_row is not None,
        "metadata_fields_used": {
            "heat_number": heat_number is not None,
            "grade": grade is not None,
            "weight_or_length": weight is not None,
        },
    }
    return RowShapeNormalizationResult(
        rows=[collapsed],
        tokens=["row_shape:vertical_mechanical_table_collapsed"],
        trace=trace,
    )


def _looks_like_heat_number(value: str) -> bool:
    canonical = re.sub(r"[^A-Z0-9]", "", value.upper())
    return bool(canonical) and any(ch.isdigit() for ch in canonical) and len(canonical) >= 4


def backfill_single_item_context(
    rows: list[dict[str, Any]],
    *,
    metadata: dict[str, Any],
) -> RowShapeNormalizationResult:
    """Backfill obvious document-level identifiers into one extracted item."""

    if len(rows) != 1:
        return RowShapeNormalizationResult(rows=rows)
    row = dict(rows[0])
    tokens: list[str] = []
    heat_number = _metadata_value(metadata, HEADER_HEAT_KEYS)
    if not row.get("heat_number") and heat_number and _looks_like_heat_number(heat_number):
        row["heat_number"] = heat_number
        tokens.append("context_propagation:heat_number_from_metadata")
    grade = _metadata_value(metadata, HEADER_GRADE_KEYS)
    if not row.get("grade") and grade:
        row["grade"] = grade
        tokens.append("context_propagation:grade_from_metadata")
    weight = _metadata_value(metadata, HEADER_WEIGHT_KEYS)
    if not row.get("weight_or_length") and weight:
        row["weight_or_length"] = weight
        tokens.append("context_propagation:weight_from_metadata")
    if not tokens:
        return RowShapeNormalizationResult(rows=rows)
    return RowShapeNormalizationResult(rows=[row], tokens=tokens, trace={"strategy": "single_item_metadata_backfill"})


def collapse_alternative_classification_rows(
    rows: list[dict[str, Any]],
    *,
    metadata: dict[str, Any],
) -> RowShapeNormalizationResult:
    """Collapse alternate classification rows for one product into one item.

    Some certificates show multiple classification rows (for example M21 and
    C1) for the same welding-wire product. When those rows share one propagated
    product grade and have no row-level heat/weight identifiers, they are
    alternate standards, not separate material items. Keep the first complete
    classification row as the item evidence and retain the others in trace.
    """

    if len(rows) < 2 or len(rows) > 4:
        return RowShapeNormalizationResult(rows=rows)
    heat_values = {_text(row.get("heat_number")) for row in rows if _text(row.get("heat_number"))}
    if len(heat_values) > 1 or any(_text(row.get("weight_or_length")) for row in rows):
        return RowShapeNormalizationResult(rows=rows)
    labels = [_classification_label(row) for row in rows]
    if not all(_has_complete_mechanicals(row) and label for row, label in zip(rows, labels)):
        return RowShapeNormalizationResult(rows=rows)
    grade = _grade_hint(metadata)
    if not grade:
        grades = {_text(row.get("grade")) for row in rows if _text(row.get("grade"))}
        if len(grades) != 1:
            return RowShapeNormalizationResult(rows=rows)
        grade = next(iter(grades))
    if _looks_like_classification_id(grade):
        return RowShapeNormalizationResult(rows=rows)

    selected = dict(rows[0])
    selected["item_id"] = None
    selected["grade"] = grade
    heat_number = _metadata_value(metadata, HEADER_HEAT_KEYS) or (next(iter(heat_values)) if heat_values else None)
    if heat_number:
        selected["heat_number"] = heat_number
    weight = _metadata_value(metadata, HEADER_WEIGHT_KEYS)
    if weight:
        selected["weight_or_length"] = weight
    trace = {
        "strategy": "alternative_classification_rows_collapsed",
        "selected_source_label": labels[0],
        "discarded_alternative_labels": labels[1:],
        "resolved_grade": grade,
        "metadata_heat_used": heat_number is not None,
    }
    return RowShapeNormalizationResult(
        rows=[selected],
        tokens=["row_shape:alternative_classification_rows_collapsed"],
        trace=trace,
    )


__all__ = [
    "RowShapeNormalizationResult",
    "backfill_single_item_context",
    "collapse_alternative_classification_rows",
    "collapse_vertical_mechanical_rows",
]
