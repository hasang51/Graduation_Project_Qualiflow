# QualiFlow Evaluation Layer

This document describes the deterministic, auditable evaluation layer added on top of the existing gold-set runner. It improves **evaluation quality** — how fairly we score extraction outputs against human annotations — without changing extraction models, review policy, or auto-accept safety logic.

## Goals

- Separate **raw exact** scoring from **business-normalized** scoring.
- Apply field-aware matchers so harmless formatting differences do not count as extraction failures.
- Keep **critical identifiers** (`heat_number`, `lot_number`, etc.) strictly matched.
- Produce structured, per-field comparison artifacts for error analysis and thesis reporting.

## What this is not

- Not a model improvement or prompt change.
- Not a replacement for human review or `review_policy` safety gates.
- Not probabilistic or LLM-based — all matchers are deterministic.

## Architecture

```text
scripts/run_eval.py
scripts/evaluate_outputs.py
        │
        ▼
evaluation/
  policy.py        # YAML field policy + grade aliases
  normalization.py # NFKC, supplier/critical normalization
  parsers.py       # dates, units, dimensions, numerics
  matchers.py      # matcher chain implementations
  metrics.py       # FieldMatchResult + aggregation
  reporting.py     # JSON / CSV / Markdown outputs

config/
  evaluation_field_policy.yaml
  grade_aliases.yaml
```

## Metrics

| Metric | Meaning |
| --- | --- |
| `raw_exact_accuracy` | Literal string equality between gold and prediction |
| `business_normalized_accuracy` | Field-aware matcher chain result |
| `accuracy_delta` | `business_normalized_accuracy - raw_exact_accuracy` |
| `harmless_normalization_accepts` | Raw fail + business pass count |
| `true_mismatches` | Both raw and business fail (excluding review band) |
| `review_needed` | Borderline supplier fuzzy matches (90–94 score) |
| `critical_identifier_mismatches` | Strict identifier failures |

Legacy `field_accuracy` from `scripts/evaluate_outputs.py` is preserved for backward compatibility.

## Field policy

`config/evaluation_field_policy.yaml` maps each field to:

- `matcher_chain` — ordered matchers; first accepting match wins
- `criticality` — `critical` or `standard`
- tolerances, unit lists, fuzzy thresholds, `empty_both_match`

### Matcher types

1. `normalized_exact_match` — NFKC, strip, collapse whitespace, lowercase
2. `semantic_equivalent_match` — explicit synonym buckets only
3. `numeric_tolerance_match` — locale-aware numeric parsing + abs/rel tolerance
4. `unit_normalized_match` — kg/t/g canonicalization via internal map
5. `date_normalized_match` — day-first dates to ISO canonical form
6. `supplier_name_fuzzy_match` — Greek Α→A, suffix normalization, RapidFuzz or token fallback
7. `grade_alias_match` — `config/grade_aliases.yaml` registry only
8. `dimension_pattern_match` — `x/×/* /by` delimiters, order-sensitive by default
9. `critical_identifier_strict_match` — trim only; no fuzzy or case folding
10. `auto_accept_safety_match` — flags unsafe processing-decision pairs for eval only

## Match result schema

Each field comparison returns:

```python
FieldMatchResult(
    field, gold_raw, pred_raw,
    raw_exact_match, business_match,
    matcher_used, criticality,
    canonical_gold, canonical_pred,
    review_needed, reason, debug,
)
```

## CLI usage

Existing commands remain valid:

```bash
python scripts/run_eval.py --metadata data/gold/metadata_20.csv --adapter mock
python scripts/evaluate_outputs.py --metadata data/gold/metadata_20.csv --predictions outputs/predictions
```

Enhanced flags:

```bash
python scripts/evaluate_outputs.py \
  --metric both \
  --field-policy config/evaluation_field_policy.yaml \
  --output-json outputs/eval_runs/latest/metrics.json \
  --output-csv outputs/eval_runs/latest/field_comparisons.csv \
  --output-md outputs/eval_runs/latest/eval_report_enhanced.md
```

`--metric` choices: `raw_exact`, `business_normalized`, `both` (default).

## Outputs

Legacy files are unchanged:

- `metrics_summary.csv`, `metrics_by_field.csv`, `failure_cases.csv`, `eval_report.md`

Enhanced layer adds:

- `metrics_by_field_enhanced.csv` — per-field raw vs business accuracy + delta
- `matcher_breakdown.csv`
- `field_comparisons.csv` — structured per-field rows
- `eval_report_enhanced.md`
- enriched `metrics.json` with `evaluation_layer` block and examples

## Motivating examples

| Gold | Prediction | Raw | Business | Matcher |
| --- | --- | --- | --- | --- |
| `07.10.2024` | `07/10/2024` | fail | pass | `date_normalized_match` |
| `2195 Kgs.` | `2195 Kgs` | fail | pass | `unit_normalized_match` |
| `NOVOFIL S.p.Α.` | `NOVOFIL S.p.A.` | fail | pass | `supplier_name_fuzzy_match` |
| `AB-123` | `AB123` | fail | fail | `critical_identifier_strict_match` |

## Dependencies

- **Required:** `pyyaml` — policy and alias YAML loading
- **Optional:** `rapidfuzz` — higher-quality supplier fuzzy scores (token fallback if absent)

No Pint/dateutil dependency — internal parsers keep evaluation deterministic and lightweight.

## Tests

```bash
python -m pytest tests/test_evaluation_layer.py -q
python -m pytest tests/ -q -k "eval"
```

## Evaluation quality vs model improvement

Improving `business_normalized_accuracy` by extending matchers or aliases measures whether predictions are **semantically equivalent** to gold — not whether the model reads PDFs better. Use:

- `raw_exact_accuracy` for strict regression baselines
- `business_normalized_accuracy` for fair human-aligned scoring
- `true_mismatches` and `critical_identifier_mismatches` for real extraction gaps

Never tune matchers to mask safety issues in production routing; `auto_accept_safety_match` is evaluation-only.
