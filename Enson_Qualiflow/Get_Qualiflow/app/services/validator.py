"""Row/document validator.

Phase 1 refactor: compliance is now tri-state. An unresolved grade or an
unresolved spec *never* becomes ``NON_COMPLIANT``; instead the validator
emits an ``UNKNOWN_GRADE`` / ``UNRESOLVED_SPEC`` outcome and a structured
review reason. See :mod:`app.domain.grade_registry`,
:mod:`app.domain.spec_registry`, and ``docs/phase1_validation_notes.md``.
"""

from __future__ import annotations

import re

from app.domain.grade_registry import GradeResolution, resolve_grade
from app.domain.outcome_taxonomy import (
    COMPLIANT,
    NEEDS_REVIEW,
    NON_COMPLIANT,
    NOT_VALIDATED,
    UNSUPPORTED_SPEC_FAMILY,
    UNRESOLVED_SPEC,
    aggregate_document_outcome,
)
from app.domain.spec_registry import (
    MaterialSpec,
    SpecResolution,
    get_spec,
    known_spec_grades,
    resolve_spec,
)
from app.schemas.extraction import UniversalDocumentExtraction, ValidationResult
from app.services.quality_thresholds import (
    ELONGATION_PERCENTAGE,
    SuspiciousBand,
    TENSILE_STRENGTH_MPA,
    YIELD_STRENGTH_MPA,
)


# Validation outcome tags (kept as exported aliases for existing imports).
OUTCOME_RESOLVED_COMPLIANT = COMPLIANT
OUTCOME_RESOLVED_NON_COMPLIANT = NON_COMPLIANT
OUTCOME_UNRESOLVED_SPEC = UNRESOLVED_SPEC
OUTCOME_UNKNOWN_GRADE = NEEDS_REVIEW
OUTCOME_AMBIGUOUS_GRADE = NEEDS_REVIEW
OUTCOME_NOT_APPLICABLE = NOT_VALIDATED
OUTCOME_EXTRACTION_UNCERTAIN = NEEDS_REVIEW


# Backward-compatibility shim. The ``/health`` endpoint and some older tests
# import ``MATERIAL_SPECS`` directly from this module. It is now materialised
# from :mod:`app.domain.spec_registry` so the two sources cannot drift.
MATERIAL_SPECS: dict[str, dict[str, float]] = {
    canonical: {
        "min_yield": _spec.min_yield_mpa,
        "min_tensile": _spec.min_tensile_mpa,
        "max_tensile": _spec.max_tensile_mpa,
        "min_elongation": _spec.min_elongation_pct,
    }
    for canonical, _spec in (
        (canonical, get_spec(canonical)) for canonical in known_spec_grades()
    )
    if _spec is not None
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


def _validate_against_spec(item, spec: MaterialSpec) -> tuple[list[str], bool, float, bool]:
    """Run the per-row spec comparison.

    Returns ``(deviations, hard_violation, row_penalty, row_suspicious)``.
    ``hard_violation`` is True only for true spec breaches (below minimum /
    outside tensile band / below min elongation). Suspicious-band trips
    contribute to ``row_penalty`` but never set ``hard_violation``.
    """

    deviations: list[str] = []
    row_penalty = 0.0
    row_suspicious = False
    hard_violation = False
    mp = item.mechanical_properties

    if mp.yield_strength_mpa is not None:
        if mp.yield_strength_mpa < spec.min_yield_mpa:
            deviations.append(
                f"Yield {mp.yield_strength_mpa:.1f} MPa below minimum {spec.min_yield_mpa:.1f} MPa"
            )
            hard_violation = True
        if _suspicious_numeric(mp.yield_strength_mpa, YIELD_STRENGTH_MPA):
            deviations.append(f"Yield {mp.yield_strength_mpa:.1f} MPa looks suspicious.")
            item.needs_review = True
            row_suspicious = True
            row_penalty += 0.18
    else:
        deviations.append("Yield missing - cannot verify.")
        row_penalty += 0.04

    if mp.tensile_strength_mpa is not None:
        if mp.tensile_strength_mpa < spec.min_tensile_mpa:
            deviations.append(
                f"Tensile {mp.tensile_strength_mpa:.1f} MPa below minimum {spec.min_tensile_mpa:.1f} MPa"
            )
            hard_violation = True
        if mp.tensile_strength_mpa > spec.max_tensile_mpa:
            deviations.append(
                f"Tensile {mp.tensile_strength_mpa:.1f} MPa above maximum {spec.max_tensile_mpa:.1f} MPa"
            )
            hard_violation = True
        if _suspicious_numeric(mp.tensile_strength_mpa, TENSILE_STRENGTH_MPA):
            deviations.append(f"Tensile {mp.tensile_strength_mpa:.1f} MPa looks suspicious.")
            item.needs_review = True
            row_suspicious = True
            row_penalty += 0.18
    else:
        deviations.append("Tensile missing - cannot verify.")
        row_penalty += 0.04

    if mp.elongation_percentage is not None:
        if mp.elongation_percentage < spec.min_elongation_pct:
            deviations.append(
                f"Elongation {mp.elongation_percentage:.1f}% below minimum {spec.min_elongation_pct:.1f}%"
            )
            hard_violation = True
        if _suspicious_numeric(mp.elongation_percentage, ELONGATION_PERCENTAGE):
            deviations.append(f"Elongation {mp.elongation_percentage:.1f}% looks suspicious.")
            item.needs_review = True
            row_suspicious = True
            row_penalty += 0.18
    else:
        deviations.append("Elongation missing - cannot verify.")
        row_penalty += 0.04

    return deviations, hard_violation, row_penalty, row_suspicious


def _record_grade_resolution(item, grade_resolution: GradeResolution, spec_resolution: SpecResolution) -> None:
    """Attach grade/spec resolution metadata to the row for UI + review pack."""

    payload = grade_resolution.to_dict()
    payload["spec"] = spec_resolution.to_dict()
    item.grade_resolution = payload
    if not item.grade_provenance:
        item.grade_provenance = "row" if grade_resolution.status != "empty" else "none"


def validate_document(data: UniversalDocumentExtraction) -> UniversalDocumentExtraction:
    review_reasons: list[str] = list(data.review_reasons)
    suspicious_rows = 0
    heat_pattern = _infer_dominant_heat_pattern(data)

    for item in data.items:
        row_penalty = 0.0
        row_suspicious = False

        # Case 1: no mechanical properties -> NOT_APPLICABLE.
        if item.mechanical_properties is None:
            grade_resolution = resolve_grade(item.grade)
            spec_resolution = resolve_spec(grade_resolution)
            _record_grade_resolution(item, grade_resolution, spec_resolution)

            deviations = ["No mechanical properties - validation skipped."]
            if _weight_or_length_is_suspicious(item.weight_or_length):
                deviations.append(
                    f"Weight/length '{item.weight_or_length}' looks malformed or lacks a clear unit."
                )
                row_penalty += 0.12
                item.needs_review = True
                review_reasons.append("malformed numeric strings")

            item.validation = ValidationResult(
                is_compliant=None,
                deviations=deviations,
                outcome=NOT_VALIDATED,
                rule_evidence=[
                    {
                        "rule": "validation_prerequisite.mechanical_properties",
                        "decision": "skipped",
                        "reason": "No mechanical properties - validation skipped.",
                    }
                ],
            )
            item.row_confidence = max(0.05, min(item.row_confidence or 1.0, 1.0) - row_penalty)
            continue

        grade_resolution = resolve_grade(item.grade)
        spec_resolution = resolve_spec(grade_resolution)
        _record_grade_resolution(item, grade_resolution, spec_resolution)

        # Case 2: unknown/empty grade -> review-safe outcome.
        if spec_resolution.status in ("empty", "unknown_grade"):
            deviations = [
                f"Unknown grade '{item.grade or '(missing)'}' - manual review required."
            ]
            item.validation = ValidationResult(
                is_compliant=None,
                deviations=deviations,
                outcome=NEEDS_REVIEW,
                rule_evidence=[
                    {
                        "rule": "spec_resolution.grade_registry",
                        "decision": "unresolved",
                        "reason": spec_resolution.reason,
                        "candidate_spec_family": list(spec_resolution.candidates),
                    }
                ],
            )
            item.needs_review = True
            item.row_confidence = max(0.05, min(item.row_confidence or 1.0, 1.0) - 0.2)
            review_reasons.append(f"unresolved_grade:{grade_resolution.raw or ''}")
            suspicious_rows += 1
            continue

        # Case 3: ambiguous grade -> review-safe outcome.
        if spec_resolution.status == "ambiguous_grade":
            candidates_display = ", ".join(spec_resolution.candidates) or "multiple candidates"
            deviations = [
                f"Ambiguous grade '{item.grade}' could match {candidates_display} - manual review required."
            ]
            item.validation = ValidationResult(
                is_compliant=None,
                deviations=deviations,
                outcome=NEEDS_REVIEW,
                rule_evidence=[
                    {
                        "rule": "spec_resolution.grade_registry",
                        "decision": "ambiguous",
                        "reason": spec_resolution.reason,
                        "candidate_spec_family": list(spec_resolution.candidates),
                    }
                ],
            )
            item.needs_review = True
            item.row_confidence = max(0.05, min(item.row_confidence or 1.0, 1.0) - 0.15)
            review_reasons.append(f"ambiguous_grade:{grade_resolution.raw or ''}")
            suspicious_rows += 1
            continue

        # Case 4: resolved grade but no declared spec -> UNRESOLVED_SPEC.
        if spec_resolution.status == "unresolved":
            deviations = [
                f"Grade '{spec_resolution.canonical or item.grade}' recognised but no spec is declared - manual review required."
            ]
            item.validation = ValidationResult(
                is_compliant=None,
                deviations=deviations,
                outcome=UNRESOLVED_SPEC,
                rule_evidence=[
                    {
                        "rule": "spec_resolution.family",
                        "decision": "unresolved_spec",
                        "reason": spec_resolution.reason,
                        "candidate_spec_family": list(spec_resolution.candidates),
                    }
                ],
            )
            item.needs_review = True
            item.row_confidence = max(0.05, min(item.row_confidence or 1.0, 1.0) - 0.1)
            review_reasons.append(f"unresolved_spec:{spec_resolution.canonical or ''}")
            continue

        if spec_resolution.status == "unsupported_spec_family":
            deviations = [
                f"Grade family '{spec_resolution.canonical or item.grade}' is recognised but not covered by deterministic rules."
            ]
            item.validation = ValidationResult(
                is_compliant=None,
                deviations=deviations,
                outcome=UNSUPPORTED_SPEC_FAMILY,
                rule_evidence=[
                    {
                        "rule": "spec_resolution.family",
                        "decision": "unsupported_spec_family",
                        "reason": spec_resolution.reason,
                        "candidate_spec_family": list(spec_resolution.candidates),
                    }
                ],
            )
            item.needs_review = True
            item.row_confidence = max(0.05, min(item.row_confidence or 1.0, 1.0) - 0.1)
            review_reasons.append("unsupported_spec_family")
            continue

        # Case 5: resolved spec -> run the compliance checks.
        assert spec_resolution.spec is not None  # narrow for type-checkers
        deviations, hard_violation, spec_penalty, spec_suspicious = _validate_against_spec(
            item, spec_resolution.spec
        )
        row_penalty += spec_penalty
        row_suspicious = row_suspicious or spec_suspicious

        if _weight_or_length_is_suspicious(item.weight_or_length):
            deviations.append(
                f"Weight/length '{item.weight_or_length}' looks malformed or lacks a clear unit."
            )
            item.needs_review = True
            row_suspicious = True
            row_penalty += 0.12
            review_reasons.append("malformed numeric strings")

        if heat_pattern and item.heat_number:
            dominant_length, dominant_digits = heat_pattern
            normalized_heat = _canonical_heat_pattern(item.heat_number)
            if (
                abs(len(normalized_heat) - dominant_length) >= 3
                or abs(sum(ch.isdigit() for ch in normalized_heat) - dominant_digits) >= 3
            ):
                deviations.append(
                    f"Heat number '{item.heat_number}' is inconsistent with the dominant pattern."
                )
                item.needs_review = True
                row_suspicious = True
                row_penalty += 0.14
                review_reasons.append("heat number format inconsistency")

        if item.weight_or_length and "," in item.weight_or_length and "." in item.weight_or_length:
            deviations.append(
                f"Weight/length '{item.weight_or_length}' mixes separators and may be misread."
            )
            item.needs_review = True
            row_suspicious = True
            row_penalty += 0.12
            review_reasons.append("mixed separators confusion")

        if _grade_spec_inconsistent(
            item.grade,
            item.mechanical_properties.yield_strength_mpa,
            item.mechanical_properties.tensile_strength_mpa,
        ):
            deviations.append(
                f"Grade '{item.grade}' is inconsistent with the extracted mechanical values."
            )
            item.needs_review = True
            row_suspicious = True
            row_penalty += 0.16
            review_reasons.append("inconsistent grade/spec combinations")

        if row_suspicious:
            review_reasons.append("numeric fields are suspicious")

        evidence = [
            {
                "rule": "spec_resolution.family",
                "decision": "resolved",
                "matched_spec_family": spec_resolution.canonical,
                "candidate_spec_family": list(spec_resolution.candidates),
                "evidence": {
                    "yield_strength_mpa": item.mechanical_properties.yield_strength_mpa,
                    "tensile_strength_mpa": item.mechanical_properties.tensile_strength_mpa,
                    "elongation_percentage": item.mechanical_properties.elongation_percentage,
                },
            }
        ]
        if hard_violation:
            outcome = NON_COMPLIANT
            is_compliant_row: bool | None = False
            evidence.append(
                {
                    "rule": "deterministic_validator.threshold_check",
                    "decision": "violation",
                    "deviations": list(deviations),
                }
            )
        else:
            outcome = COMPLIANT
            is_compliant_row = True
            evidence.append(
                {
                    "rule": "deterministic_validator.threshold_check",
                    "decision": "pass",
                }
            )

        item.validation = ValidationResult(
            is_compliant=is_compliant_row,
            deviations=deviations,
            outcome=outcome,
            rule_evidence=evidence,
        )
        item.row_confidence = max(0.05, min(item.row_confidence or 1.0, 1.0) - row_penalty)
        if row_suspicious:
            suspicious_rows += 1

    row_outcomes = [item.validation.outcome for item in data.items if item.validation is not None]
    data.outcome = aggregate_document_outcome([entry for entry in row_outcomes if entry])
    data.is_compliant = True if data.outcome == COMPLIANT else False if data.outcome == NON_COMPLIANT else None

    if data.total_items_detected != len(data.items):
        data.needs_review = True
        review_reasons.append("row count mismatches")
        data.total_items_detected = len(data.items)

    if data.items and suspicious_rows / len(data.items) >= 0.35:
        data.needs_review = True
        review_reasons.append("too many rows are suspicious")

    data.review_reasons = sorted(set(review_reasons))
    return data
