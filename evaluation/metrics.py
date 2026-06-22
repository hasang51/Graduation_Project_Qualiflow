"""Field comparison orchestration and metric aggregation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from evaluation.matchers import run_matcher_chain
from evaluation.normalization import is_missing, raw_exact_equal, to_raw_string
from evaluation.policy import EvaluationPolicy


@dataclass
class FieldMatchResult:
    field: str
    gold_raw: str
    pred_raw: str
    raw_exact_match: bool
    business_match: bool
    matcher_used: str
    criticality: str
    canonical_gold: str
    canonical_pred: str
    review_needed: bool = False
    reason: str = ""
    debug: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload.get("debug") is None:
            payload.pop("debug", None)
        return payload


def compare_values(
    field_name: str,
    gold: object | None,
    pred: object | None,
    policy: EvaluationPolicy,
) -> FieldMatchResult:
    field_policy = policy.for_field(field_name)
    gold_raw = to_raw_string(gold)
    pred_raw = to_raw_string(pred)
    raw_match = raw_exact_equal(gold, pred)
    outcome = run_matcher_chain(field_name, gold, pred, field_policy, policy)
    return FieldMatchResult(
        field=field_name,
        gold_raw=gold_raw,
        pred_raw=pred_raw,
        raw_exact_match=raw_match,
        business_match=outcome.business_match,
        matcher_used=outcome.matcher_used,
        criticality=field_policy.criticality,
        canonical_gold=outcome.canonical_gold,
        canonical_pred=outcome.canonical_pred,
        review_needed=outcome.review_needed,
        reason=outcome.reason,
        debug=outcome.debug,
    )


def _split_scalar_or_list(value: object | None) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    text = str(value)
    if "|" in text:
        return [chunk.strip() for chunk in text.split("|") if chunk.strip()]
    return [value]


def compare_list_field(
    field_name: str,
    gold: object | None,
    pred: object | None,
    policy: EvaluationPolicy,
) -> FieldMatchResult:
    gold_parts = _split_scalar_or_list(gold)
    pred_parts = _split_scalar_or_list(pred)
    if is_missing(gold) and is_missing(pred):
        return compare_values(field_name, gold, pred, policy)
    if len(gold_parts) != len(pred_parts):
        return FieldMatchResult(
            field=field_name,
            gold_raw=to_raw_string(gold),
            pred_raw=to_raw_string(pred),
            raw_exact_match=False,
            business_match=False,
            matcher_used="list_length_mismatch",
            criticality=policy.for_field(field_name).criticality,
            canonical_gold=to_raw_string(gold),
            canonical_pred=to_raw_string(pred),
            reason="list length mismatch",
        )
    if not gold_parts:
        return compare_values(field_name, gold, pred, policy)
    pair_results = [compare_values(field_name, g, p, policy) for g, p in zip(gold_parts, pred_parts)]
    raw_match = all(item.raw_exact_match for item in pair_results)
    business_match = all(item.business_match for item in pair_results)
    review_needed = any(item.review_needed for item in pair_results)
    return FieldMatchResult(
        field=field_name,
        gold_raw=to_raw_string(gold),
        pred_raw=to_raw_string(pred),
        raw_exact_match=raw_match,
        business_match=business_match,
        matcher_used=pair_results[0].matcher_used,
        criticality=policy.for_field(field_name).criticality,
        canonical_gold="|".join(item.canonical_gold for item in pair_results),
        canonical_pred="|".join(item.canonical_pred for item in pair_results),
        review_needed=review_needed,
        reason="all list items matched" if business_match else "list item mismatch",
        debug={"pair_count": len(pair_results)},
    )


LIST_LIKE_FIELDS = {
    "heat_number",
    "heat_numbers",
    "grade",
    "grades",
    "yield_strength_mpa",
    "tensile_strength_mpa",
    "elongation_percentage",
    "item_id",
    "weight_or_length",
}


def compare_field(
    field_name: str,
    gold: object | None,
    pred: object | None,
    policy: EvaluationPolicy,
) -> FieldMatchResult:
    gold_parts = _split_scalar_or_list(gold)
    pred_parts = _split_scalar_or_list(pred)
    if len(gold_parts) > 1 or len(pred_parts) > 1 or field_name in LIST_LIKE_FIELDS:
        if isinstance(gold, list) or isinstance(pred, list) or "|" in to_raw_string(gold) or "|" in to_raw_string(pred):
            return compare_list_field(field_name, gold, pred, policy)
    return compare_values(field_name, gold, pred, policy)


def run_field_evaluation(
    *,
    field_names: Iterable[str],
    gold_fields: dict[str, Any],
    pred_fields: dict[str, Any],
    policy: EvaluationPolicy,
    prediction_missing: bool = False,
) -> list[FieldMatchResult]:
    results: list[FieldMatchResult] = []
    for field_name in field_names:
        gold_value = gold_fields.get(field_name)
        if is_missing(gold_value):
            continue
        pred_value = pred_fields.get(field_name)
        if prediction_missing:
            results.append(
                FieldMatchResult(
                    field=field_name,
                    gold_raw=to_raw_string(gold_value),
                    pred_raw="",
                    raw_exact_match=False,
                    business_match=False,
                    matcher_used="missing_prediction",
                    criticality=policy.for_field(field_name).criticality,
                    canonical_gold=to_raw_string(gold_value),
                    canonical_pred="",
                    reason="missing prediction file or field",
                )
            )
            continue
        results.append(compare_field(field_name, gold_value, pred_value, policy))
    return results


@dataclass
class EvaluationAggregate:
    n_comparisons: int = 0
    raw_exact_hits: int = 0
    business_hits: int = 0
    raw_exact_accuracy: float = 0.0
    business_normalized_accuracy: float = 0.0
    accuracy_delta: float = 0.0
    harmless_normalization_accepts: int = 0
    true_mismatches: int = 0
    review_needed: int = 0
    critical_identifier_mismatches: int = 0
    matcher_used: dict[str, int] = field(default_factory=dict)
    per_field_raw: dict[str, float] = field(default_factory=dict)
    per_field_business: dict[str, float] = field(default_factory=dict)
    examples_raw_fail_business_pass: list[FieldMatchResult] = field(default_factory=list)
    examples_both_fail: list[FieldMatchResult] = field(default_factory=list)
    examples_critical_fail: list[FieldMatchResult] = field(default_factory=list)


def aggregate_field_results(results: Iterable[FieldMatchResult], *, max_examples: int = 5) -> EvaluationAggregate:
    rows = list(results)
    n = len(rows)
    raw_hits = sum(1 for row in rows if row.raw_exact_match)
    business_hits = sum(1 for row in rows if row.business_match)
    harmless = sum(1 for row in rows if (not row.raw_exact_match) and row.business_match)
    true_mismatch = sum(1 for row in rows if (not row.raw_exact_match) and (not row.business_match) and not row.review_needed)
    review_needed = sum(1 for row in rows if row.review_needed)
    critical_id_mismatch = sum(
        1
        for row in rows
        if row.criticality == "critical"
        and row.matcher_used == "critical_identifier_strict_match"
        and not row.business_match
    )

    matcher_counts: dict[str, int] = {}
    per_field_raw: dict[str, list[bool]] = {}
    per_field_business: dict[str, list[bool]] = {}
    for row in rows:
        matcher_counts[row.matcher_used] = matcher_counts.get(row.matcher_used, 0) + 1
        per_field_raw.setdefault(row.field, []).append(row.raw_exact_match)
        per_field_business.setdefault(row.field, []).append(row.business_match)

    aggregate = EvaluationAggregate(
        n_comparisons=n,
        raw_exact_hits=raw_hits,
        business_hits=business_hits,
        raw_exact_accuracy=round(raw_hits / n, 4) if n else 0.0,
        business_normalized_accuracy=round(business_hits / n, 4) if n else 0.0,
        harmless_normalization_accepts=harmless,
        true_mismatches=true_mismatch,
        review_needed=review_needed,
        critical_identifier_mismatches=critical_id_mismatch,
        matcher_used=matcher_counts,
        per_field_raw={field: round(sum(vals) / len(vals), 4) for field, vals in per_field_raw.items()},
        per_field_business={field: round(sum(vals) / len(vals), 4) for field, vals in per_field_business.items()},
    )
    aggregate.accuracy_delta = round(
        aggregate.business_normalized_accuracy - aggregate.raw_exact_accuracy,
        4,
    )
    aggregate.examples_raw_fail_business_pass = [
        row for row in rows if (not row.raw_exact_match) and row.business_match
    ][:max_examples]
    aggregate.examples_both_fail = [
        row for row in rows if (not row.raw_exact_match) and (not row.business_match) and not row.review_needed
    ][:max_examples]
    aggregate.examples_critical_fail = [
        row
        for row in rows
        if row.criticality == "critical" and not row.business_match
    ][:max_examples]
    return aggregate
