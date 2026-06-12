# QualiFlow Evaluation Report

- metadata: `data\gold\metadata_20.csv`
- predictions: `outputs\eval_runs\live_eval_20260612_1632`
- documents evaluated: 20

## Metrics

| metric | value |
| --- | --- |
| n_documents | 20 |
| field_accuracy | 0.619 |
| critical_field_accuracy | 0.6875 |
| document_type_accuracy | 0.55 |
| processing_decision_accuracy | 0.1 |
| review_rate | 0.85 |
| unsafe_auto_accept_rate | 0.5 |
| missing_required_field_rate | 0.0446 |
| average_latency_ms | 38821.2 |

## Method

String fields are compared by exact match after lowercase conversion, whitespace trimming, and internal whitespace collapse. Numeric fields use a tolerance when both gold and predicted values are numeric. Missing prediction fields are counted as incorrect whenever a gold value exists.

Processing decision accuracy is computed only when the gold annotation provides `processing_decision`, or a derivable `review_required` label. `unsafe_auto_accept_rate` measures gold review-required documents that the prediction marks as not requiring review.

## No Fabricated Metrics

This report only summarizes values computed from the provided metadata, ground truth JSON files, and prediction JSON files. Missing gold labels are skipped from metric denominators, and missing predictions are reported in `failure_cases.csv` instead of being filled with invented values.

Failure cases written: 80
