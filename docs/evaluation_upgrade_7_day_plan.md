# Evaluation Layer — 7-Day Practical Plan

This plan upgrades QualiFlow gold-set evaluation from naive string equality to a production-oriented, auditable layer **without** changing extraction models or review safety.

## Day 1 — Audit and baseline freeze

- [x] Inventory `scripts/run_eval.py`, `scripts/evaluate_outputs.py`, gold schema, existing tests.
- [x] Capture current `field_accuracy` on `metadata_20.csv` as legacy baseline.
- [ ] Run `python scripts/evaluate_outputs.py` on latest predictions; archive `metrics_summary.csv`.

**Exit criteria:** Legacy command and metrics unchanged; baseline numbers recorded.

## Day 2 — Policy and module skeleton

- [x] Add `config/evaluation_field_policy.yaml` and `config/grade_aliases.yaml`.
- [x] Create `evaluation/` package: `policy`, `normalization`, `parsers`, `matchers`, `metrics`, `reporting`.
- [x] Define `FieldMatchResult` schema.

**Exit criteria:** Policy loads; unit tests run for normalization/parsers.

## Day 3 — Core matchers

- [x] Implement date, unit, numeric, normalized exact, semantic, critical identifier matchers.
- [x] Parametrized tests for date/unit/critical cases from acceptance criteria.

**Exit criteria:** Motivating date and weight examples pass.

## Day 4 — Supplier, grade, dimensions

- [x] Supplier fuzzy matcher with Greek Α→A and suffix normalization.
- [x] Grade alias registry (no runtime invention).
- [x] Dimension pattern matcher with order-sensitive default.

**Exit criteria:** NOVOFIL Greek-alpha example and dimension example pass.

## Day 5 — Reporting and CLI integration

- [x] Wire enhanced metrics into `evaluate_outputs.py` and `run_eval.py`.
- [x] Add `--metric`, `--field-policy`, `--output-json/csv/md`.
- [x] Emit matcher breakdown and example blocks.

**Exit criteria:** Full eval run produces legacy + enhanced artifacts.

## Day 6 — Gold-set validation and error analysis

- [ ] Run enhanced eval on all 20 gold documents with real predictions.
- [ ] Review `harmless_normalization_accepts` vs `true_mismatches`.
- [ ] Triage `critical_identifier_mismatches` manually — never relax strict rules to pass tests.
- [ ] Add missing grade aliases only when gold annotator confirms equivalence.

**Exit criteria:** Written error-analysis notes; no safety-layer changes.

## Day 7 — Documentation, CI, handoff

- [x] `docs/evaluation_layer.md` (this upgrade).
- [ ] Add CI step: `pytest tests/test_evaluation_layer.py` and `pytest -k eval`.
- [ ] Present before/after `raw_exact_accuracy` vs `business_normalized_accuracy` in thesis/pilot deck.
- [ ] Optional: install `rapidfuzz` in eval environment for supplier scoring.

**Exit criteria:** Team can reproduce metrics; CI green; stakeholders understand eval vs model improvements.

## Risk controls

| Risk | Mitigation |
| --- | --- |
| Fuzzy critical IDs | `critical_identifier_strict_match` only; regression tests |
| Inflated business accuracy | Report `accuracy_delta` and `true_mismatches` alongside |
| Alias drift | Registry-driven `grade_aliases.yaml`; human sign-off |
| Breaking legacy CLI | Keep `field_accuracy`; enhanced metrics are additive |

## Commands checklist

```bash
pip install pyyaml
# optional: pip install rapidfuzz

python -m pytest tests/test_evaluation_layer.py -q
python -m pytest tests/ -q -k "eval"

python scripts/evaluate_outputs.py \
  --metadata data/gold/metadata_20.csv \
  --predictions outputs/predictions \
  --metric both
```

## Success metrics

- `raw_exact_accuracy` available on every run
- `business_normalized_accuracy` ≥ `raw_exact_accuracy` on formatting-heavy gold (expected)
- `critical_identifier_mismatches` unchanged when only punctuation differs on IDs (strict fail is correct)
- Zero changes to `review_policy.py` / `extraction_finalizer.py`
