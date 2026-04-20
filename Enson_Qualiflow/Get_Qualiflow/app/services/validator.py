from __future__ import annotations

import re

from app.schemas.extraction import UniversalDocumentExtraction, ValidationResult
from app.services.quality_thresholds import (
    ELONGATION_PERCENTAGE,
    SuspiciousBand,
    TENSILE_STRENGTH_MPA,
    YIELD_STRENGTH_MPA,
)

MATERIAL_SPECS = {
    "S355J2+N": {"min_yield": 355.0, "min_tensile": 470.0, "max_tensile": 630.0, "min_elongation": 22.0},
    "S355J2": {"min_yield": 355.0, "min_tensile": 470.0, "max_tensile": 630.0, "min_elongation": 22.0},
    "S235JR": {"min_yield": 235.0, "min_tensile": 360.0, "max_tensile": 510.0, "min_elongation": 26.0},
    "S275JR": {"min_yield": 275.0, "min_tensile": 410.0, "max_tensile": 560.0, "min_elongation": 23.0},
    "API 5L X65": {"min_yield": 448.0, "min_tensile": 531.0, "max_tensile": 758.0, "min_elongation": 18.0},
}


def _suspicious_numeric(value: float, band: SuspiciousBand) -> bool:
    return band.is_suspicious(value)


def _weight_or_length_is_suspicious(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.strip().lower()
    if not any(char.isdigit() for char in lowered):
        return True
    if "," in lowered and "." in lowered:
        return True
    valid_units = ("kg", "mt", "ton", "tons", "m", "mm", "cm", "ft", "pcs", "pc")
    if not any(unit in lowered for unit in valid_units):
        return not bool(re.search(r"\d+(?:[.,]\d+)?", lowered))
    return False


def _canonical_heat_pattern(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _infer_dominant_heat_pattern(data: UniversalDocumentExtraction) -> tuple[int, int] | None:
    canonical_values = [_canonical_heat_pattern(item.heat_number) for item in data.items if item.heat_number]
    if len(canonical_values) < 2:
        return None
    lengths = [len(value) for value in canonical_values]
    digit_counts = [sum(char.isdigit() for char in value) for value in canonical_values]
    dominant_length = max(set(lengths), key=lengths.count)
    dominant_digits = max(set(digit_counts), key=digit_counts.count)
    return dominant_length, dominant_digits


def _grade_spec_inconsistent(item_grade: str | None, yield_value: float | None, tensile_value: float | None) -> bool:
    if not item_grade:
        return False
    grade_key = item_grade.upper()
    if "S235" in grade_key and yield_value is not None and yield_value > 420:
        return True
    if "S355" in grade_key and yield_value is not None and yield_value < 250:
        return True
    if "X65" in grade_key and tensile_value is not None and tensile_value < 430:
        return True
    return False


def validate_document(data: UniversalDocumentExtraction) -> UniversalDocumentExtraction:
    all_compliant = True
    items_with_mech = 0
    review_reasons: list[str] = list(data.review_reasons)
    suspicious_rows = 0
    heat_pattern = _infer_dominant_heat_pattern(data)

    for item in data.items:
        row_penalty = 0.0
        row_suspicious = False

        if item.mechanical_properties is None:
            item.validation = ValidationResult(
                is_compliant=True,
                deviations=["No mechanical properties - validation skipped."],
            )
            if _weight_or_length_is_suspicious(item.weight_or_length):
                item.validation.deviations.append(
                    f"Weight/length '{item.weight_or_length}' looks malformed or lacks a clear unit."
                )
                row_penalty += 0.12
                row_suspicious = True
                item.needs_review = True
                review_reasons.append("malformed numeric strings")
            item.row_confidence = max(0.05, min(item.row_confidence or 1.0, 1.0) - row_penalty)
            continue

        items_with_mech += 1
        mp = item.mechanical_properties
        deviations: list[str] = []
        grade = (item.grade or "").strip()
        spec = MATERIAL_SPECS.get(grade) or MATERIAL_SPECS.get(grade.upper())

        if spec is None:
            deviations.append(f"Unknown grade '{item.grade}' - manual review required.")
            item.validation = ValidationResult(is_compliant=False, deviations=deviations)
            item.needs_review = True
            item.row_confidence = max(0.05, min(item.row_confidence or 1.0, 1.0) - 0.2)
            all_compliant = False
            review_reasons.append("grade/spec validation is impossible")
            suspicious_rows += 1
            continue

        if mp.yield_strength_mpa is not None:
            if mp.yield_strength_mpa < spec["min_yield"]:
                deviations.append(f"Yield {mp.yield_strength_mpa:.1f} MPa below minimum {spec['min_yield']:.1f} MPa")
            if _suspicious_numeric(mp.yield_strength_mpa, YIELD_STRENGTH_MPA):
                deviations.append(f"Yield {mp.yield_strength_mpa:.1f} MPa looks suspicious.")
                item.needs_review = True
                row_suspicious = True
                row_penalty += 0.18
                review_reasons.append("numeric fields are suspicious")
        else:
            deviations.append("Yield missing - cannot verify.")
            row_penalty += 0.04

        if mp.tensile_strength_mpa is not None:
            if mp.tensile_strength_mpa < spec["min_tensile"]:
                deviations.append(
                    f"Tensile {mp.tensile_strength_mpa:.1f} MPa below minimum {spec['min_tensile']:.1f} MPa"
                )
            if mp.tensile_strength_mpa > spec["max_tensile"]:
                deviations.append(
                    f"Tensile {mp.tensile_strength_mpa:.1f} MPa above maximum {spec['max_tensile']:.1f} MPa"
                )
            if _suspicious_numeric(mp.tensile_strength_mpa, TENSILE_STRENGTH_MPA):
                deviations.append(f"Tensile {mp.tensile_strength_mpa:.1f} MPa looks suspicious.")
                item.needs_review = True
                row_suspicious = True
                row_penalty += 0.18
                review_reasons.append("numeric fields are suspicious")
        else:
            deviations.append("Tensile missing - cannot verify.")
            row_penalty += 0.04

        if mp.elongation_percentage is not None:
            if mp.elongation_percentage < spec["min_elongation"]:
                deviations.append(f"Elongation {mp.elongation_percentage:.1f}% below minimum {spec['min_elongation']:.1f}%")
            if _suspicious_numeric(mp.elongation_percentage, ELONGATION_PERCENTAGE):
                deviations.append(f"Elongation {mp.elongation_percentage:.1f}% looks suspicious.")
                item.needs_review = True
                row_suspicious = True
                row_penalty += 0.18
                review_reasons.append("numeric fields are suspicious")
        else:
            deviations.append("Elongation missing - cannot verify.")
            row_penalty += 0.04

        if _weight_or_length_is_suspicious(item.weight_or_length):
            deviations.append(f"Weight/length '{item.weight_or_length}' looks malformed or lacks a clear unit.")
            item.needs_review = True
            row_suspicious = True
            row_penalty += 0.12
            review_reasons.append("malformed numeric strings")

        if heat_pattern and item.heat_number:
            dominant_length, dominant_digits = heat_pattern
            normalized_heat = _canonical_heat_pattern(item.heat_number)
            if abs(len(normalized_heat) - dominant_length) >= 3 or abs(sum(char.isdigit() for char in normalized_heat) - dominant_digits) >= 3:
                deviations.append(f"Heat number '{item.heat_number}' is inconsistent with the dominant pattern.")
                item.needs_review = True
                row_suspicious = True
                row_penalty += 0.14
                review_reasons.append("heat number format inconsistency")

        if item.weight_or_length and "," in item.weight_or_length and "." in item.weight_or_length:
            deviations.append(f"Weight/length '{item.weight_or_length}' mixes separators and may be misread.")
            item.needs_review = True
            row_suspicious = True
            row_penalty += 0.12
            review_reasons.append("mixed separators confusion")

        if _grade_spec_inconsistent(item.grade, mp.yield_strength_mpa, mp.tensile_strength_mpa):
            deviations.append(f"Grade '{item.grade}' is inconsistent with the extracted mechanical values.")
            item.needs_review = True
            row_suspicious = True
            row_penalty += 0.16
            review_reasons.append("inconsistent grade/spec combinations")

        item.validation = ValidationResult(is_compliant=len(deviations) == 0, deviations=deviations)
        item.row_confidence = max(0.05, min(item.row_confidence or 1.0, 1.0) - row_penalty)
        if deviations:
            all_compliant = False
        if row_suspicious:
            suspicious_rows += 1

    if items_with_mech == 0:
        data.is_compliant = None
    else:
        data.is_compliant = all_compliant

    if data.total_items_detected != len(data.items):
        data.needs_review = True
        review_reasons.append("row count mismatches")
        data.total_items_detected = len(data.items)

    if data.items and suspicious_rows / len(data.items) >= 0.35:
        data.needs_review = True
        review_reasons.append("too many rows are suspicious")

    data.review_reasons = sorted(set(review_reasons))
    return data
