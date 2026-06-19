# QualiFlow — Agent Guide

QualiFlow is a human-in-the-loop AI document verification system for **Mill Test Certificates (MTC)** and related industrial quality certificates. It extracts structured fields from PDFs, validates them deterministically, and routes uncertain cases to human review rather than silent approval.

**Design principle:** when in doubt, escalate to review. Auto-accept is a narrow, auditable exception—not the default outcome.

---

## Hard Safety Rules

These rules are non-negotiable. Any change that weakens them is a regression.

1. **Never auto-accept `severe_scan` documents.**
2. **Never auto-accept if grade is missing, unresolved, ambiguous, or explicitly unmapped.**
3. **Never auto-accept if `heat_number` or any accepted traceability identifier is missing, unverified, OCR-uncertain, or conflicting.**
4. **Never auto-accept if row/table alignment is uncertain.**
5. **Confidence-only reasons must be separated from real blocking reasons.**
6. **An `auto_accept` decision must include an explainable `auto_accept_evidence` object.**
7. **The finalizer must never clear real blocking reasons.**
8. **Any change to review policy must add or update regression tests.**
9. **Do not modify extraction prompts unless tests prove the decision layer needs prompt-level metadata.**
10. **Prefer small, auditable patches over broad rewrites.**

---

## Decision Layer (where safety logic lives)

| Concern | Primary module | Tests |
| --- | --- | --- |
| Review gating & blocking reasons | `app/services/review_policy.py` | `tests/test_review_policy.py` |
| Final reconciliation & auto-accept | `app/services/extraction_finalizer.py` | `tests/test_extraction_finalizer.py` |
| Confidence vs. blocking separation | `app/services/confidence.py` | `tests/test_conservative_decision_confidence.py` |
| Traceability verification | `app/services/traceability.py` | `tests/test_traceability.py` |
| Identifier guard (OCR uncertainty) | `app/services/identifier_verification_guard.py` | `tests/test_identifier_verification_guard.py` |
| Mechanical table alignment | `app/services/mechanical_table_mapper.py` | `tests/test_mechanical_table_mapper.py` |
| Grade resolution | `app/domain/grade_registry.py` | `tests/test_grade_registry.py` |
| Document quality profiling | `app/services/document_profiler.py` | `tests/test_document_profiler.py` |
| End-to-end safety regressions | — | `tests/test_auto_accept_safety_regression.py` |

### Blocking vs. confidence-only reasons

- **Blocking** examples: `missing_critical_field:*`, `traceability_unverified`, `critical_identifier_unverified`, `mechanical_table_alignment_uncertain`, `traceability_identifier_ocr_uncertain`, `traceability_identifier_conflict`, `unresolved_spec`, `unsupported_spec_family`, `validation_conflict:*`, `row_count_inconsistent`.
- **Confidence-only** examples: `confidence_below_threshold`, `confidence falls below threshold`, `low_confidence:*`. These may be stripped during confidence-exempt reconciliation; they must never mask a blocking reason.

### `auto_accept_evidence`

When emitting `auto_accept`, populate `auto_accept_evidence` with a structured, human-readable audit trail (e.g. verified traceability identifiers, compliant validation outcome, confidence summary, and which gates were checked). Do not auto-accept without this object.

---

## Change Workflow

1. **Identify the layer.** Safety bugs usually belong in `review_policy.py` or `extraction_finalizer.py`, not in extraction prompts.
2. **Add or update a regression test first** (or in the same patch) that reproduces the unsafe case.
3. **Make the smallest fix** that satisfies the test and the hard safety rules above.
4. **Run validation commands** (below) before considering the change done.
5. **Do not** broaden auto-accept paths, lower thresholds, or strip blocking tokens to make tests pass.

---

## Validation Commands

Run these after any review-policy, finalizer, or auto-accept change:

```bash
python -m pytest tests/test_review_policy.py tests/test_extraction_finalizer.py tests/test_conservative_decision_confidence.py -q
python -m pytest tests/test_auto_accept_safety_regression.py -q
```

---

## Repository Layout (quick reference)

```text
app/
  main.py                  # FastAPI entry
  routes/extraction.py     # Upload & pipeline orchestration
  services/
    extraction_pipeline.py # Multimodal Stage A/B extraction
    extraction_finalizer.py
    review_policy.py
    confidence.py
    traceability.py
    validator.py
  domain/                  # Grade/spec registries, identifier parsing
frontend/src/              # React UI
tests/                     # Unit & regression tests
scripts/run_eval.py        # Gold-set evaluation
data/gold/                 # Ground-truth annotations
```

---

## What agents should avoid

- Rewriting the extraction pipeline or prompts to fix a decision-layer bug.
- Clearing `review_reasons`, `blocking_reasons`, or structured tokens in the finalizer to force `auto_accept`.
- Treating document quality (`severe_scan`, `noisy_scan`) as sufficient evidence for auto-accept.
- Large refactors across review policy, finalizer, and confidence in a single change.
- Committing secrets (`.env`, API keys).
