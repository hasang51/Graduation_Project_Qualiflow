# QualiFlow Live Evaluation Summary

**Run:** `live_eval_20260612_1632`  
**Date:** 2026-06-12  
**Metadata:** `data/gold/metadata_20.csv`  
**Documents root:** `data/eval_docs`  
**Pipeline:** existing (mode D, routed hybrid)  
**Documents processed:** 20 / 20  
**Failed PDFs:** none

## Aggregate Metrics

| Metric | Value |
| --- | --- |
| n_documents | 20 |
| field_accuracy | 0.619 (61.9%) |
| critical_field_accuracy | 0.6875 (68.8%) |
| document_type_accuracy | 0.55 (55.0%) |
| processing_decision_accuracy | 0.1 (10.0%) |
| review_rate | 0.85 (85.0%) |
| unsafe_auto_accept_rate | 0.5 (50.0%) |
| missing_required_field_rate | 0.0446 (4.5%) |
| average_latency_ms | 38821.2 (~38.8 sec) |

## Field Metrics

| Field | Samples | Correct | Accuracy |
| --- | --- | --- | --- |
| grade | 20 | 6 | 30.0% |
| heat_number | 19 | 11 | 57.9% |
| yield_strength_mpa | 17 | 13 | 76.5% |
| tensile_strength_mpa | 19 | 13 | 68.4% |
| elongation_percentage | 17 | 14 | 82.4% |
| weight_or_length | 18 | 6 | 33.3% |
| item_id | 20 | 15 | 75.0% |
| certificate_date | 20 | 10 | 50.0% |

## Notes

- All 20 PDFs in `data/eval_docs` were processed with the current extraction pipeline, validator, and review policy.
- Predictions saved to `outputs/eval_runs/live_eval_20260612_1632/doc001.json` … `doc020.json`.
- Ground truth compared against `data/gold/ground_truth/`.
- PDF parsing warnings (`incorrect startxref pointer`) appeared for some scanned documents but did not block extraction.
