# QualiFlow — Pilot Study Status

> Last updated: 2026-04-20

This document tracks the progression from full-corpus profiling through live
extraction and toward verified gold evaluation. It is framed as a **pilot
study** consistent with resource-constrained academic research.

---

## Corpus overview

| layer | count | status |
| --- | --- | --- |
| Full corpus (Mill Test Certificates) | 103 PDFs | **profiled** |
| Balanced candidate subset | 20 docs | **selected** |
| Live pilot subset (initial) | 3 docs | **extracted (live)** |
| Live pilot subset (expansion) | +5 docs | **extracted (live)** |
| Verified gold | 0 docs | **pending human review** |

---

## Quality distribution of the full corpus

| quality_class | count | % |
| --- | --- | --- |
| digital_clean | ~35 | ~34 % |
| scan_clean | ~45 | ~44 % |
| noisy_scan | ~23 | ~22 % |

_(from `data/manifests/profile_summary.csv`)_

---

## Balanced 20-document candidate subset

Selected to represent the quality distribution of the full corpus.
Location: `data/gold_candidates/gold_candidates_manifest.{jsonl,csv}`

| quality_class | docs in subset |
| --- | --- |
| digital_clean | 6 |
| scan_clean | 8 |
| noisy_scan | 6 |

---

## Live pilot extraction — initial 3 docs (2026-04-20)

All 3 successful live docs were `noisy_scan`. The Anthropic org rate limit
(30 000 input tokens / minute) interrupted the run after doc 3.

| filename | quality_class | route | pages_sent | confidence | items | review |
| --- | --- | --- | --- | --- | --- | --- |
| Screenshot_3-output.pdf | noisy_scan | preprocessed_multimodal | 1 | 0.85 | 1 | NEEDS_REVIEW |
| 001125.pdf | noisy_scan | preprocessed_multimodal | 2 | 0.85 | 1 | NEEDS_REVIEW |
| 1ff62aadb0ec3dc42572e2d090067615.pdf | noisy_scan | preprocessed_multimodal | 3 | 0.32 | 0 | NEEDS_REVIEW |

Batch run: `data/batch_runs/20260420T_live_full/`

---

## Next scheduled extraction — 5 docs (Phase B)

Selected from the remaining 17 candidates by `scripts/select_next_live_docs.py`.
Optimisation objective: max diversity, min pages-sent, exclude severe-blur.

| filename | quality_class | pages_sent (est.) | cost_bucket |
| --- | --- | --- | --- |
| GRN16192.pdf | digital_clean | 1 | low |
| STAL 316 L.pdf | scan_clean | 1 | low |
| Outokumpu.pdf | noisy_scan | 1 | low |
| S355MC-Dry-8.05-x-914.6.pdf | digital_clean | 2 | medium |
| 20160919104079247924.pdf | scan_clean | 1 | low |

Selection file: `data/gold_candidates/next_5_live_docs.{csv,jsonl}`

---

## Token-cost optimisations applied (Phase A)

| optimisation | description |
| --- | --- |
| `BatchRunPolicy` | Central config: max 5 new live docs, 2–3 pages per doc, $2.00 budget cap, stop on 2nd rate limit. |
| `page_selector.py` | Deterministic page ranking — prefers page 1 + table-present pages, caps by quality class. |
| Metadata dedup fix | `_metadata_blocks` no longer sends `full_gray` on page 1 when it equals the primary variant. |
| Row extraction trim | `_row_extraction_blocks` sends only `table_crop` + `adaptive_binary` (or one full-page) per page, removing redundant variants. |
| Usage logging | Both LLM stages now capture `input_tokens`, `output_tokens` per call into `llm_usage` in the per-doc JSON. |
| Usage CSV | Each live batch run now writes `data/batch_runs/<ts>/usage.csv`. |
| `--resume` always on | Policy defaults `use_resume=True` so already-extracted docs are never re-billed. |

---

## Provisional evaluation results (8 live docs — combined pilot)

> ⚠ **PROVISIONAL** — gold is PREANNOTATED ONLY. Do not cite these as final thesis results.

| metric | 3-doc initial | 8-doc combined |
| --- | --- | --- |
| n_documents | 3 | **8** |
| field_accuracy | 1.000 | **1.000** |
| critical_field_accuracy | 1.000 | **1.000** |
| compliance_decision_accuracy | 1.000 | **1.000** |
| review_rate | 1.000 | **1.000** |
| stp_rate | 0.000 | **0.000** |
| avg_latency_ms | 54 751 | **36 706** |
| p95_latency_ms | 104 620 | **104 620** |
| extraction_completeness | 0.778 | **0.896** |

The avg_latency improvement from 54 s → 37 s reflects the 5-doc expansion
including shorter single-page digital docs. Completeness rose from 0.78 to 0.90
because the new docs had fewer missing fields.

High review_rate is expected: all docs trigger at least one review token
(`validation_conflict:row_non_compliant` for compliance failures;
`document_quality:noisy_scan` for degraded scans). The review policy is
working as designed — it flags everything for human sign-off when no verified
gold exists.

---

## Gold verification path

```
annotation_sheet.csv            # PREANNOTATED — fill verified_* columns
        │
        ▼ (human review)
scripts/promote_verified_gold.py
        │
        ▼
data/gold_verified/annotations.{csv,jsonl}  # VERIFIED GOLD
        │
        ▼
python -m scripts.run_eval --mode D --run-dir ... --gold data/gold_verified/annotations.jsonl
        │
        ▼
data/eval_outputs/...  # AUTHORITATIVE METRICS (no --provisional)
```

### Reviewer instructions

1. Open `data/gold_candidates/annotation_sheet.csv`.
2. For each row, verify the `extracted_*` values against the actual PDF.
3. Fill the `verified_*` columns with the correct values.
4. Set `review_status` to `VERIFIED` (or `ACCEPTED` / `OK`).
5. Run `python -m scripts.promote_verified_gold`.
6. Re-run evaluation: `python -m scripts.run_eval --mode D --run-dir ...`.

Human-readable summary of the 3 live extractions: `data/gold_candidates/reviewer_pack.md`

---

## What remains manual

| item | who | when |
| --- | --- | --- |
| Verify annotation_sheet.csv for 3 initial live docs | Human reviewer | Before thesis submission |
| Verify annotation_sheet.csv for 5 expansion docs | Human reviewer | After Phase B runs |
| Add more verified gold for robustness | Human reviewer | Optional, improves metric reliability |
| Run final authoritative evaluation | Researcher | After verified gold is complete |

---

## Accepted thesis framing

This study uses the following language:

- "A full corpus of 103 Mill Test Certificates was profiled using a
  deterministic image quality classifier."
- "A balanced 20-document candidate subset was selected to represent the
  quality distribution of the full corpus."
- "An initial live pilot was executed on 3 documents; the extraction pipeline
  completed successfully for all 3."
- "A low-cost expansion to 5 additional documents was planned and executed
  under a strict token-budget policy."
- "Provisional accuracy metrics are reported against preannotated labels;
  final authoritative metrics require human gold verification."

Do **not** use:
- "100-document evaluation" (only 3–8 docs were live-extracted in this phase)
- "verified accuracy = 1.0" (the gold is not yet human-verified)
- "production-ready" or "SaaS" language
