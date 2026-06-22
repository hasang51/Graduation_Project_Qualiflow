"""Field-aware matchers for deterministic evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evaluation.normalization import (
    is_missing,
    normalize_critical_identifier,
    normalize_exact,
    normalize_supplier_name,
    raw_exact_equal,
    to_raw_string,
)
from evaluation.parsers import (
    parse_date,
    parse_dimension,
    parse_numeric,
    parse_unit_value,
)
from evaluation.policy import EvaluationPolicy, FieldPolicy

try:
    from rapidfuzz import fuzz

    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False


SEMANTIC_SYNONYMS: dict[str, set[str]] = {
    "yes": {"yes", "y", "true", "1"},
    "no": {"no", "n", "false", "0"},
    "review": {"review", "needs_review", "manual_review", "true", "yes"},
    "auto_accept": {"auto_accept", "accepted", "pass", "false", "no"},
    "compliant": {"compliant", "pass", "ok", "conform", "conforming"},
    "non_compliant": {"non_compliant", "fail", "nonconforming", "non conforming"},
    "mill test certificate": {"mill test certificate", "mtc", "mill certificate", "test certificate"},
    "certificate of analysis": {"certificate of analysis", "coa", "cert of analysis"},
    "cif": {"cif", "cost insurance freight"},
    "fob": {"fob", "free on board"},
    "exw": {"exw", "ex works"},
}


@dataclass(frozen=True)
class MatcherOutcome:
    business_match: bool
    matcher_used: str
    canonical_gold: str
    canonical_pred: str
    review_needed: bool = False
    reason: str = ""
    debug: dict[str, Any] | None = None


def _semantic_bucket(value: object | None) -> str | None:
    normalized = normalize_exact(value)
    if not normalized:
        return None
    for bucket, synonyms in SEMANTIC_SYNONYMS.items():
        if normalized in synonyms:
            return bucket
    return normalized


def _grade_canonical_set(value: object | None, policy: EvaluationPolicy) -> set[str]:
    text = normalize_exact(value)
    if not text:
        return set()
    found: set[str] = {text}
    for canonical, aliases in policy.grade_aliases.items():
        canonical_norm = normalize_exact(canonical)
        alias_norms = {normalize_exact(alias) for alias in aliases}
        if text == canonical_norm or text in alias_norms:
            found.add(canonical_norm)
            found.update(alias_norms)
    return found


def _token_overlap_ratio(a: str, b: str) -> float:
    tokens_a = {token for token in a.split() if token}
    tokens_b = {token for token in b.split() if token}
    if not tokens_a or not tokens_b:
        return 0.0
    overlap = len(tokens_a & tokens_b)
    return 100.0 * overlap / max(len(tokens_a), len(tokens_b))


def _supplier_similarity(a: str, b: str) -> float:
    if _HAS_RAPIDFUZZ:
        return float(fuzz.token_sort_ratio(a, b))
    return _token_overlap_ratio(a, b)


def match_normalized_exact(gold: object | None, pred: object | None, _: FieldPolicy) -> MatcherOutcome:
    gold_norm = normalize_exact(gold)
    pred_norm = normalize_exact(pred)
    return MatcherOutcome(
        business_match=gold_norm == pred_norm,
        matcher_used="normalized_exact_match",
        canonical_gold=gold_norm,
        canonical_pred=pred_norm,
        reason="normalized strings equal" if gold_norm == pred_norm else "normalized strings differ",
    )


def match_semantic_equivalent(gold: object | None, pred: object | None, _: FieldPolicy) -> MatcherOutcome:
    gold_bucket = _semantic_bucket(gold)
    pred_bucket = _semantic_bucket(pred)
    match = gold_bucket is not None and gold_bucket == pred_bucket
    return MatcherOutcome(
        business_match=match,
        matcher_used="semantic_equivalent_match",
        canonical_gold=gold_bucket or "",
        canonical_pred=pred_bucket or "",
        reason="semantic bucket match" if match else "semantic bucket mismatch",
    )


def match_numeric_tolerance(gold: object | None, pred: object | None, policy: FieldPolicy) -> MatcherOutcome:
    gold_unit = parse_unit_value(gold)
    pred_unit = parse_unit_value(pred)
    if gold_unit and pred_unit and (gold_unit.unit or pred_unit.unit):
        return MatcherOutcome(
            business_match=False,
            matcher_used="numeric_tolerance_match",
            canonical_gold=to_raw_string(gold),
            canonical_pred=to_raw_string(pred),
            reason="values carry units; use unit_normalized_match",
        )
    gold_num = parse_numeric(gold)
    pred_num = parse_numeric(pred)
    if gold_num is None or pred_num is None:
        return MatcherOutcome(
            business_match=False,
            matcher_used="numeric_tolerance_match",
            canonical_gold=to_raw_string(gold),
            canonical_pred=to_raw_string(pred),
            reason="non-numeric value",
        )
    diff = abs(gold_num.value - pred_num.value)
    rel = diff / max(abs(gold_num.value), 1e-9)
    match = diff <= policy.numeric_abs_tolerance or rel <= policy.numeric_rel_tolerance
    return MatcherOutcome(
        business_match=match,
        matcher_used="numeric_tolerance_match",
        canonical_gold=str(gold_num.value),
        canonical_pred=str(pred_num.value),
        reason="within tolerance" if match else "outside tolerance",
        debug={"abs_diff": diff, "rel_diff": rel},
    )


def match_unit_normalized(gold: object | None, pred: object | None, policy: FieldPolicy) -> MatcherOutcome:
    gold_parsed = parse_unit_value(gold)
    pred_parsed = parse_unit_value(pred)
    if gold_parsed is None or pred_parsed is None:
        return MatcherOutcome(
            business_match=False,
            matcher_used="unit_normalized_match",
            canonical_gold=to_raw_string(gold),
            canonical_pred=to_raw_string(pred),
            reason="unit parse failed",
        )
    if gold_parsed.canonical_kg is not None and pred_parsed.canonical_kg is not None:
        diff = abs(gold_parsed.canonical_kg - pred_parsed.canonical_kg)
        rel = diff / max(abs(gold_parsed.canonical_kg), 1e-9)
        match = diff <= policy.numeric_abs_tolerance or rel <= policy.numeric_rel_tolerance
        canonical_gold = f"{gold_parsed.canonical_kg:.6g} kg"
        canonical_pred = f"{pred_parsed.canonical_kg:.6g} kg"
        reason = "mass equivalent" if match else "mass not equivalent"
    elif gold_parsed.unit and pred_parsed.unit and gold_parsed.unit == pred_parsed.unit:
        diff = abs(gold_parsed.value - pred_parsed.value)
        rel = diff / max(abs(gold_parsed.value), 1e-9)
        match = diff <= policy.numeric_abs_tolerance or rel <= policy.numeric_rel_tolerance
        canonical_gold = f"{gold_parsed.value} {gold_parsed.unit}"
        canonical_pred = f"{pred_parsed.value} {pred_parsed.unit}"
        reason = "same unit within tolerance" if match else "same unit outside tolerance"
    else:
        match = (
            gold_parsed.value == pred_parsed.value
            and normalize_exact(gold_parsed.unit) == normalize_exact(pred_parsed.unit)
        )
        canonical_gold = f"{gold_parsed.value} {gold_parsed.unit}".strip()
        canonical_pred = f"{pred_parsed.value} {pred_parsed.unit}".strip()
        reason = "value+unit match" if match else "unit mismatch"
    return MatcherOutcome(
        business_match=match,
        matcher_used="unit_normalized_match",
        canonical_gold=canonical_gold,
        canonical_pred=canonical_pred,
        reason=reason,
    )


def match_date_normalized(gold: object | None, pred: object | None, policy: FieldPolicy) -> MatcherOutcome:
    gold_date = parse_date(gold, allow_incomplete=policy.allow_incomplete_dates)
    pred_date = parse_date(pred, allow_incomplete=policy.allow_incomplete_dates)
    if gold_date is None or pred_date is None:
        return MatcherOutcome(
            business_match=False,
            matcher_used="date_normalized_match",
            canonical_gold=to_raw_string(gold),
            canonical_pred=to_raw_string(pred),
            reason="incomplete or unparseable date",
        )
    match = gold_date.iso == pred_date.iso
    return MatcherOutcome(
        business_match=match,
        matcher_used="date_normalized_match",
        canonical_gold=gold_date.iso,
        canonical_pred=pred_date.iso,
        reason="iso date match" if match else "iso date mismatch",
    )


def match_supplier_fuzzy(gold: object | None, pred: object | None, policy: FieldPolicy) -> MatcherOutcome:
    gold_norm = normalize_supplier_name(gold)
    pred_norm = normalize_supplier_name(pred)
    score = _supplier_similarity(gold_norm, pred_norm)
    if score >= policy.supplier_fuzzy_threshold_accept:
        return MatcherOutcome(
            business_match=True,
            matcher_used="supplier_name_fuzzy_match",
            canonical_gold=gold_norm,
            canonical_pred=pred_norm,
            review_needed=False,
            reason=f"fuzzy score {score:.1f} >= accept threshold",
            debug={"score": score},
        )
    if score >= policy.supplier_fuzzy_threshold_review:
        return MatcherOutcome(
            business_match=False,
            matcher_used="supplier_name_fuzzy_match",
            canonical_gold=gold_norm,
            canonical_pred=pred_norm,
            review_needed=True,
            reason=f"fuzzy score {score:.1f} in review band",
            debug={"score": score},
        )
    return MatcherOutcome(
        business_match=False,
        matcher_used="supplier_name_fuzzy_match",
        canonical_gold=gold_norm,
        canonical_pred=pred_norm,
        reason=f"fuzzy score {score:.1f} below review threshold",
        debug={"score": score},
    )


def match_grade_alias(gold: object | None, pred: object | None, policy: EvaluationPolicy) -> MatcherOutcome:
    gold_set = _grade_canonical_set(gold, policy)
    pred_set = _grade_canonical_set(pred, policy)
    if not gold_set or not pred_set:
        return MatcherOutcome(
            business_match=False,
            matcher_used="grade_alias_match",
            canonical_gold=normalize_exact(gold),
            canonical_pred=normalize_exact(pred),
            reason="empty grade",
        )
    match = bool(gold_set & pred_set)
    return MatcherOutcome(
        business_match=match,
        matcher_used="grade_alias_match",
        canonical_gold="|".join(sorted(gold_set)),
        canonical_pred="|".join(sorted(pred_set)),
        reason="alias intersection" if match else "no alias intersection",
    )


def _dimension_signature(parsed, *, order_insensitive: bool) -> tuple:
    parts = [(round(value, 6), unit) for value, unit in parsed.parts]
    if order_insensitive:
        return tuple(sorted(parts))
    return tuple(parts)


def match_dimension_pattern(gold: object | None, pred: object | None, policy: FieldPolicy) -> MatcherOutcome:
    gold_dim = parse_dimension(gold)
    pred_dim = parse_dimension(pred)
    if gold_dim is None or pred_dim is None:
        return MatcherOutcome(
            business_match=False,
            matcher_used="dimension_pattern_match",
            canonical_gold=to_raw_string(gold),
            canonical_pred=to_raw_string(pred),
            reason="dimension parse failed",
        )
    gold_sig = _dimension_signature(gold_dim, order_insensitive=policy.dimension_order_insensitive)
    pred_sig = _dimension_signature(pred_dim, order_insensitive=policy.dimension_order_insensitive)
    match = gold_sig == pred_sig and normalize_exact(gold_dim.unit) == normalize_exact(pred_dim.unit)
    return MatcherOutcome(
        business_match=match,
        matcher_used="dimension_pattern_match",
        canonical_gold=str(gold_sig),
        canonical_pred=str(pred_sig),
        reason="dimension signature match" if match else "dimension signature mismatch",
    )


def match_critical_identifier(gold: object | None, pred: object | None, _: FieldPolicy) -> MatcherOutcome:
    gold_norm = normalize_critical_identifier(gold)
    pred_norm = normalize_critical_identifier(pred)
    return MatcherOutcome(
        business_match=gold_norm == pred_norm,
        matcher_used="critical_identifier_strict_match",
        canonical_gold=gold_norm,
        canonical_pred=pred_norm,
        reason="strict identifier match" if gold_norm == pred_norm else "strict identifier mismatch",
    )


def match_auto_accept_safety(gold: object | None, pred: object | None, _: FieldPolicy) -> MatcherOutcome:
    """Safety gate: gold review_required=true must not be predicted as auto_accept."""
    gold_review = _semantic_bucket(gold)
    pred_review = _semantic_bucket(pred)
    gold_requires_review = gold_review == "review"
    pred_auto_accept = pred_review == "auto_accept"
    if gold_requires_review and pred_auto_accept:
        return MatcherOutcome(
            business_match=False,
            matcher_used="auto_accept_safety_match",
            canonical_gold=gold_review or "",
            canonical_pred=pred_review or "",
            reason="unsafe auto_accept when gold requires review",
        )
    exact = normalize_exact(gold) == normalize_exact(pred)
    return MatcherOutcome(
        business_match=exact,
        matcher_used="auto_accept_safety_match",
        canonical_gold=normalize_exact(gold),
        canonical_pred=normalize_exact(pred),
        reason="processing decision aligned" if exact else "processing decision mismatch",
    )


MATCHERS = {
    "normalized_exact_match": match_normalized_exact,
    "semantic_equivalent_match": match_semantic_equivalent,
    "numeric_tolerance_match": match_numeric_tolerance,
    "unit_normalized_match": match_unit_normalized,
    "date_normalized_match": match_date_normalized,
    "supplier_name_fuzzy_match": match_supplier_fuzzy,
    "grade_alias_match": None,  # needs policy
    "dimension_pattern_match": match_dimension_pattern,
    "critical_identifier_strict_match": match_critical_identifier,
    "auto_accept_safety_match": match_auto_accept_safety,
}


def run_matcher_chain(
    field_name: str,
    gold: object | None,
    pred: object | None,
    field_policy: FieldPolicy,
    policy: EvaluationPolicy,
) -> MatcherOutcome:
    if is_missing(gold) and is_missing(pred):
        if field_policy.empty_both_match:
            return MatcherOutcome(
                business_match=True,
                matcher_used="empty_both",
                canonical_gold="",
                canonical_pred="",
                reason="both empty per policy",
            )
        return MatcherOutcome(
            business_match=False,
            matcher_used="empty_both",
            canonical_gold="",
            canonical_pred="",
            reason="empty values not allowed for this field",
        )
    if is_missing(gold) or is_missing(pred):
        return MatcherOutcome(
            business_match=False,
            matcher_used="missing_value",
            canonical_gold=to_raw_string(gold),
            canonical_pred=to_raw_string(pred),
            reason="one side missing",
        )

    for matcher_name in field_policy.matcher_chain:
        if matcher_name == "grade_alias_match":
            outcome = match_grade_alias(gold, pred, policy)
        else:
            matcher_fn = MATCHERS.get(matcher_name)
            if matcher_fn is None:
                continue
            outcome = matcher_fn(gold, pred, field_policy)
        if outcome.business_match or outcome.review_needed:
            return outcome
    return MatcherOutcome(
        business_match=False,
        matcher_used=field_policy.matcher_chain[-1] if field_policy.matcher_chain else "none",
        canonical_gold=normalize_exact(gold),
        canonical_pred=normalize_exact(pred),
        reason="no matcher accepted",
    )
