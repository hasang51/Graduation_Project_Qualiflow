# Adaptive Preprocessing Strategy

## Purpose

Stage 3 stabilizes preprocessing so document quality conditions drive variant selection instead of a one-size-fits-all path.

This is not OCR integration.  
This is not architecture redesign.  
It is an adaptive, deterministic strategy layer on top of the existing preprocessing pipeline.

## Available variants

Current explicit variants:

- `full_gray`
- `denoised`
- `contrast` (contrast-enhanced)
- `adaptive_binary`
- `sharpened`
- `table_crop` (zoomed crop around the detected table region, when a table is found)
- `table_line_mask` (debug/table-detection support)

## Quality metrics

Deterministic metrics are computed per page:

- `blur_score`: variance of Laplacian (lower means blurrier)
- `noise_estimate`: stddev of residual between source and median-blurred image

Thresholds (from `app/services/preprocessing_strategy.py`):

- Blur:
  - `high` if `blur_score < 80`
  - `moderate` if `80 <= blur_score < 150`
  - `low` if `blur_score >= 150`
- Noise:
  - `high` if `noise_estimate >= 25`
  - `moderate` if `14 <= noise_estimate < 25`
  - `low` if `noise_estimate < 14`

Derived condition:

- `clean`
- `noisy`
- `blurry`
- `noisy_and_blurry`

## Selection strategy

Variant selection is deterministic and explainable:

- Noisy pages prioritize: `denoised`, `adaptive_binary`, `contrast`
- Blurry pages prioritize: `sharpened`, `contrast`
- Clean pages prioritize: `full_gray`, `contrast`
- If table crop exists: prioritize `table_crop`
- Backward-compatible fallbacks keep required support variants available

Primary full-page variant is selected from:

- `contrast`, `sharpened`, `denoised`, `full_gray`, `adaptive_binary`

## Recorded metadata

Each page records:

- `quality_assessment`
  - `blur_score`
  - `noise_estimate`
  - `blur_severity`
  - `noise_severity`
  - `detected_condition`
- `variant_selection`
  - `available_variants`
  - `selected_variants`
  - `primary_variant`
  - `selection_reasoning`

Document-level summary in preprocessing metadata:

- `adaptive_preprocessing_summary`
  - `condition_counts`
  - `dominant_condition`
  - `strategy_version`

## Why clean/noisy/blurry should differ

Noise and blur degrade text/table visibility differently:

- Noise-heavy scans benefit from denoising + binarization for structural recovery.
- Blur-heavy scans benefit from sharpening + contrast boosting.
- Clean pages avoid over-processing and preserve details.

This stabilization enables inspectable, reproducible preprocessing decisions that feed the Claude-based extraction stage with variants suited to each document condition.

