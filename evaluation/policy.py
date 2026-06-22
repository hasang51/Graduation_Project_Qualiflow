"""Load evaluation field policy and grade alias registries."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = PROJECT_ROOT / "config" / "evaluation_field_policy.yaml"
DEFAULT_GRADE_ALIASES_PATH = PROJECT_ROOT / "config" / "grade_aliases.yaml"


@dataclass(frozen=True)
class FieldPolicy:
    field_type: str = "text"
    criticality: str = "standard"
    matcher_chain: tuple[str, ...] = ("normalized_exact_match",)
    empty_both_match: bool = True
    numeric_abs_tolerance: float = 1.0
    numeric_rel_tolerance: float = 0.01
    supplier_fuzzy_threshold_accept: int = 95
    supplier_fuzzy_threshold_review: int = 90
    dimension_order_insensitive: bool = False
    allow_incomplete_dates: bool = False
    canonical_units: tuple[str, ...] = ()


@dataclass
class EvaluationPolicy:
    defaults: FieldPolicy
    fields: dict[str, FieldPolicy] = field(default_factory=dict)
    grade_aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def for_field(self, field_name: str) -> FieldPolicy:
        if field_name in self.fields:
            return self.fields[field_name]
        return self.defaults


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required to load evaluation policy files. "
            "Install with: pip install pyyaml"
        ) from exc
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping in {path}")
    return payload


def _field_policy_from_mapping(defaults: FieldPolicy, mapping: dict[str, Any]) -> FieldPolicy:
    chain = mapping.get("matcher_chain", defaults.matcher_chain)
    if isinstance(chain, str):
        chain = [chain]
    units = mapping.get("canonical_units", defaults.canonical_units)
    return FieldPolicy(
        field_type=str(mapping.get("field_type", defaults.field_type)),
        criticality=str(mapping.get("criticality", defaults.criticality)),
        matcher_chain=tuple(str(item) for item in chain),
        empty_both_match=bool(mapping.get("empty_both_match", defaults.empty_both_match)),
        numeric_abs_tolerance=float(mapping.get("numeric_abs_tolerance", defaults.numeric_abs_tolerance)),
        numeric_rel_tolerance=float(mapping.get("numeric_rel_tolerance", defaults.numeric_rel_tolerance)),
        supplier_fuzzy_threshold_accept=int(
            mapping.get("supplier_fuzzy_threshold_accept", defaults.supplier_fuzzy_threshold_accept)
        ),
        supplier_fuzzy_threshold_review=int(
            mapping.get("supplier_fuzzy_threshold_review", defaults.supplier_fuzzy_threshold_review)
        ),
        dimension_order_insensitive=bool(
            mapping.get("dimension_order_insensitive", defaults.dimension_order_insensitive)
        ),
        allow_incomplete_dates=bool(mapping.get("allow_incomplete_dates", defaults.allow_incomplete_dates)),
        canonical_units=tuple(str(item) for item in units),
    )


def load_grade_aliases(path: Path | None = None) -> dict[str, tuple[str, ...]]:
    alias_path = path or DEFAULT_GRADE_ALIASES_PATH
    payload = _load_yaml(alias_path)
    aliases_raw = payload.get("aliases") or {}
    result: dict[str, tuple[str, ...]] = {}
    for canonical, alias_list in aliases_raw.items():
        canonical_key = str(canonical).strip()
        aliases = tuple(str(item).strip() for item in (alias_list or []) if str(item).strip())
        result[canonical_key] = aliases
    return result


def load_evaluation_policy(
    policy_path: Path | None = None,
    grade_aliases_path: Path | None = None,
) -> EvaluationPolicy:
    path = policy_path or DEFAULT_POLICY_PATH
    payload = _load_yaml(path)
    defaults_mapping = payload.get("defaults") or {}
    defaults = _field_policy_from_mapping(FieldPolicy(), defaults_mapping)

    fields: dict[str, FieldPolicy] = {}
    for field_name, mapping in (payload.get("fields") or {}).items():
        if not isinstance(mapping, dict):
            continue
        fields[str(field_name)] = _field_policy_from_mapping(defaults, mapping)

    grade_aliases = load_grade_aliases(grade_aliases_path)
    return EvaluationPolicy(defaults=defaults, fields=fields, grade_aliases=grade_aliases)


def policy_debug_snapshot(policy: EvaluationPolicy) -> str:
    return json.dumps(
        {
            "defaults": policy.defaults.__dict__,
            "field_count": len(policy.fields),
            "grade_alias_count": len(policy.grade_aliases),
        },
        indent=2,
        sort_keys=True,
    )
