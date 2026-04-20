"""Metric primitives for the QualiFlow evaluation harness.

Designed to be importable (no CLI side-effects). Used by :mod:`scripts.run_eval`
and the unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Iterable

CRITICAL_FIELDS = (
    "supplier_name",
    "document_type",
    "heat_numbers",
    "grades",
    "yield_strength_mpa",
    "tensile_strength_mpa",
)

SIMPLE_FIELDS = ("supplier_name", "document_type", "certificate_date")
LIST_STRING_FIELDS = ("heat_numbers", "grades")
LIST_NUMERIC_FIELDS = ("yield_strength_mpa", "tensile_strength_mpa", "elongation_percentage")
ALL_FIELDS = SIMPLE_FIELDS + LIST_STRING_FIELDS + LIST_NUMERIC_FIELDS


@dataclass
class FieldComparison:
    field: str
    equal: bool
    gold: Any = None
    predicted: Any = None


@dataclass
class DocumentEvaluation:
    document_id: str
    filename: str
    mode: str | None = None
    route_used: str | None = None
    quality_class: str | None = None
    field_hits: int = 0
    field_total: int = 0
    critical_hits: int = 0
    critical_total: int = 0
    compliance_correct: bool | None = None
    review_required: bool | None = None
    latency_ms: float | None = None
    completeness: float | None = None
    comparisons: list[FieldComparison] = field(default_factory=list)


def _normalise_string(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _normalise_list_string(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = [str(v).strip() for v in value if v not in (None, "")]
    else:
        items = [chunk.strip() for chunk in str(value).split("|") if chunk.strip()]
    return sorted({_normalise_string(item) for item in items if _normalise_string(item)})


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalise_list_float(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value).split("|")
    cleaned: list[float] = []
    for item in raw:
        parsed = _coerce_float(item)
        if parsed is not None:
            cleaned.append(round(parsed, 2))
    return sorted(cleaned)


def _lists_equal_float(a: list[float], b: list[float], tolerance: float = 1.0) -> bool:
    if len(a) != len(b):
        return False
    a_sorted, b_sorted = sorted(a), sorted(b)
    return all(abs(x - y) <= tolerance for x, y in zip(a_sorted, b_sorted))


def compare_field(field_name: str, gold_value: Any, predicted_value: Any) -> FieldComparison:
    if field_name in SIMPLE_FIELDS:
        eq = _normalise_string(gold_value) == _normalise_string(predicted_value)
        return FieldComparison(field=field_name, equal=eq, gold=gold_value, predicted=predicted_value)
    if field_name in LIST_STRING_FIELDS:
        a = _normalise_list_string(gold_value)
        b = _normalise_list_string(predicted_value)
        return FieldComparison(field=field_name, equal=a == b, gold=a, predicted=b)
    if field_name in LIST_NUMERIC_FIELDS:
        a = _normalise_list_float(gold_value)
        b = _normalise_list_float(predicted_value)
        return FieldComparison(field=field_name, equal=_lists_equal_float(a, b), gold=a, predicted=b)
    return FieldComparison(field=field_name, equal=gold_value == predicted_value, gold=gold_value, predicted=predicted_value)


def predicted_fields_from_extraction(extraction: dict) -> dict[str, Any]:
    items = extraction.get("items") or []
    heats = [item.get("heat_number") for item in items if item.get("heat_number")]
    grades = [item.get("grade") for item in items if item.get("grade")]
    yields: list[float] = []
    tensiles: list[float] = []
    elongs: list[float] = []
    for item in items:
        mp = item.get("mechanical_properties") or {}
        if mp.get("yield_strength_mpa") is not None:
            yields.append(float(mp["yield_strength_mpa"]))
        if mp.get("tensile_strength_mpa") is not None:
            tensiles.append(float(mp["tensile_strength_mpa"]))
        if mp.get("elongation_percentage") is not None:
            elongs.append(float(mp["elongation_percentage"]))
    return {
        "supplier_name": extraction.get("supplier_name"),
        "document_type": extraction.get("document_type"),
        "certificate_date": extraction.get("certificate_date"),
        "is_compliant": extraction.get("is_compliant"),
        "heat_numbers": heats,
        "grades": grades,
        "yield_strength_mpa": yields,
        "tensile_strength_mpa": tensiles,
        "elongation_percentage": elongs,
    }


def evaluate_document(
    *,
    gold_record: dict,
    per_document: dict,
) -> DocumentEvaluation:
    extraction = per_document.get("extraction") or {}
    predicted = predicted_fields_from_extraction(extraction)

    comparisons: list[FieldComparison] = []
    field_hits = 0
    field_total = 0
    critical_hits = 0
    critical_total = 0

    for field_name in ALL_FIELDS:
        comp = compare_field(field_name, gold_record.get(field_name), predicted.get(field_name))
        comparisons.append(comp)
        field_total += 1
        if comp.equal:
            field_hits += 1
        if field_name in CRITICAL_FIELDS:
            critical_total += 1
            if comp.equal:
                critical_hits += 1

    # Compliance comparison
    compliance_correct: bool | None = None
    if gold_record.get("is_compliant") is not None:
        gold_compliant = bool(gold_record.get("is_compliant"))
        predicted_compliant = extraction.get("is_compliant")
        if predicted_compliant is None:
            compliance_correct = False
        else:
            compliance_correct = bool(predicted_compliant) == gold_compliant

    # Completeness = fraction of critical fields where we produced *any* value
    produced = 0
    for field_name in CRITICAL_FIELDS:
        value = predicted.get(field_name)
        if isinstance(value, list):
            if value:
                produced += 1
        else:
            if value not in (None, ""):
                produced += 1
    completeness = produced / len(CRITICAL_FIELDS)

    return DocumentEvaluation(
        document_id=per_document.get("document_id") or gold_record.get("document_id"),
        filename=per_document.get("filename") or gold_record.get("filename") or "",
        mode=per_document.get("mode"),
        route_used=per_document.get("route_used"),
        quality_class=(per_document.get("profile") or {}).get("quality_class"),
        field_hits=field_hits,
        field_total=field_total,
        critical_hits=critical_hits,
        critical_total=critical_total,
        compliance_correct=compliance_correct,
        review_required=extraction.get("needs_review"),
        latency_ms=per_document.get("latency_ms"),
        completeness=round(completeness, 4),
        comparisons=comparisons,
    )


def aggregate_metrics(evaluations: Iterable[DocumentEvaluation]) -> dict[str, float | int]:
    evaluations = list(evaluations)
    n = len(evaluations)
    if n == 0:
        return {
            "n": 0,
            "field_accuracy": 0.0,
            "critical_field_accuracy": 0.0,
            "compliance_decision_accuracy": 0.0,
            "review_rate": 0.0,
            "stp_rate": 0.0,
            "average_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "extraction_completeness": 0.0,
        }
    total_field = sum(ev.field_total for ev in evaluations) or 1
    total_field_hits = sum(ev.field_hits for ev in evaluations)
    total_critical = sum(ev.critical_total for ev in evaluations) or 1
    total_critical_hits = sum(ev.critical_hits for ev in evaluations)
    compliance_samples = [ev.compliance_correct for ev in evaluations if ev.compliance_correct is not None]
    compliance_accuracy = (sum(1 for v in compliance_samples if v) / len(compliance_samples)) if compliance_samples else 0.0
    review_samples = [ev.review_required for ev in evaluations if ev.review_required is not None]
    review_rate = (sum(1 for v in review_samples if v) / len(review_samples)) if review_samples else 0.0
    stp_rate = 1.0 - review_rate
    latencies = [ev.latency_ms for ev in evaluations if ev.latency_ms is not None]
    average_latency = mean(latencies) if latencies else 0.0
    if latencies:
        sorted_latencies = sorted(latencies)
        idx = max(0, min(len(sorted_latencies) - 1, int(round(0.95 * (len(sorted_latencies) - 1)))))
        p95_latency = sorted_latencies[idx]
    else:
        p95_latency = 0.0
    completeness_samples = [ev.completeness for ev in evaluations if ev.completeness is not None]
    avg_completeness = mean(completeness_samples) if completeness_samples else 0.0
    return {
        "n": n,
        "field_accuracy": round(total_field_hits / total_field, 4),
        "critical_field_accuracy": round(total_critical_hits / total_critical, 4),
        "compliance_decision_accuracy": round(compliance_accuracy, 4),
        "review_rate": round(review_rate, 4),
        "stp_rate": round(stp_rate, 4),
        "average_latency_ms": round(average_latency, 1),
        "p95_latency_ms": round(p95_latency, 1),
        "extraction_completeness": round(avg_completeness, 4),
    }
