# Runtime architecture — QualiFlow Phase 2

The runtime for `POST /api/v1/extract` is a strict single-path pipeline:

```
upload → profile → route → preprocess → extract → validate → confidence → review → persist
```

This document specifies the deterministic behaviour of the profiler, router, and review policy. Anthropic / Stage A / Stage B prompts are intentionally out of scope — Phase 2 adds nothing new to the prompts.

## 1. Document profiler

Module: `app/services/document_profiler.py`. Entry point: `profile_document(pdf_path) -> DocumentProfile`.

Fields produced:

| Field | Type | How it is computed |
| --- | --- | --- |
| `document_id` | str | `sha256(file)[:16]` (passed in by the batch runner; defaults to `pdf_path.stem`). |
| `filename` | str | `Path.name`. |
| `page_count` | int | From `pypdf.PdfReader`. Falls back to the number of rasterised sample pages if `pypdf` cannot open the file. |
| `has_text_layer` | bool | True when at least 50% of pages emit ≥ 40 stripped characters. |
| `text_density` | float in [0, 1] | `min(1.0, avg_chars_per_page / 2000)`. |
| `blur_score` | float | `min(compute_blur_score(page))` across the first 2 rasterised pages (worst-page blur). |
| `noise_score` | float | `max(estimate_noise(page))` across the first 2 rasterised pages (worst-page noise). |
| `table_presence_hint` | bool | True if any sample page has a horizontal ink run ≥ 40% of the image width. |
| `quality_class` | `digital_clean` \| `scan_clean` \| `scan_degraded` | See the decision table below. |
| `reasons` | list[str] | Human-readable reasons for the classification. |

### Quality-class decision table

| has_text_layer | text_density | blur_score | noise_score | quality_class |
| --- | --- | --- | --- | --- |
| true | ≥ 0.02 | ≥ 80 | < 25 | `digital_clean` |
| true | ≥ 0.02 | < 80 OR ≥ 25 | — | `scan_degraded` (when both moderate+) OR `scan_clean` |
| any | — | < 80 | — | `scan_degraded` (blur_high) |
| any | — | — | ≥ 25 | `scan_degraded` (noise_high) |
| any | — | < 150 | ≥ 14 | `scan_degraded` (both moderate) |
| false | — | ≥ 80 | < 25 | `scan_clean` |

Thresholds are defined as module constants so tests can pin them (`BLUR_DEGRADED_THRESHOLD`, `NOISE_DEGRADED_THRESHOLD`, `BLUR_MODERATE_THRESHOLD`, `NOISE_MODERATE_THRESHOLD`, `DIGITAL_TEXT_DENSITY_MIN`).

### Why only the first 2 pages

Profiling runs on every PDF in the dataset. Rasterising a 50-page scan at full DPI for profiling alone is wasteful — the profiler only needs "worst-page" estimates to decide the route. Text-layer detection still runs on every page (it is cheap and PDF-native).

## 2. Extraction router

Module: `app/services/extraction_router.py`. Entry points:
- `choose_route(profile) -> RouteDecision`
- `force_route(name) -> RouteDecision` — used by experiment modes B and C.

Mapping:

| `quality_class` | `route` | Variant stack chosen by `preprocessing_strategy.variants_for_route` |
| --- | --- | --- |
| `digital_clean` | `native_multimodal` | `full_gray`, `contrast` |
| `scan_clean` | `rendered_multimodal` | `full_gray`, `contrast`, `sharpened` (fallback) |
| `scan_degraded` | `preprocessed_multimodal` | `denoised`, `adaptive_binary`, `sharpened`, `table_crop` (if detected) |

The router returns exactly one route per document — there is no fan-out. Forcing a route (`--force-route` / `--mode B/C` in the batch runner) bypasses the profiler but still goes through the rest of the pipeline, which keeps experiments comparable.

## 3. Preprocessing coupling

Module: `app/services/preprocessing.py`. Signature:

```python
def preprocess_pdf(pdf_path, artifact_dir, route: str | None = None)
```

When `route` is `None` the per-page condition-based selection behaves exactly as before Phase 2. When `route` is supplied, the page-level selection is replaced by `variants_for_route(route, …)`. The route is recorded in `meta["route_used"]` so downstream tooling (batch runner, eval) can audit it.

## 4. Review policy

Module: `app/services/review_policy.py`. Entry point: `apply_review_policy(extraction, *, profile, preprocessing_meta, review_confidence_threshold)`.

The function is **deterministic**, **auditable**, and **additive** — it does not discard the validator's or the confidence normaliser's free-form reasons; it appends structured `key:value` tokens on top.

### Token catalogue

| Token | Trigger |
| --- | --- |
| `missing_critical_field:heat_number` | `heat_number` missing on every row. |
| `missing_critical_field:grade` | `grade` missing on every row. |
| `missing_critical_field:yield_strength` | `yield_strength_mpa` missing on every row. |
| `missing_critical_field:tensile_strength` | `tensile_strength_mpa` missing on every row. |
| `document_quality:scan_degraded` | `profile.quality_class == "scan_degraded"`. |
| `document_quality:scan_clean` | `profile.quality_class == "scan_clean"` AND (low confidence OR no items). |
| `low_confidence:yield_strength` | Final confidence < threshold AND yield is suspicious/missing AND profile is scan_degraded. |
| `low_confidence:tensile_strength` | Same as above for tensile. |
| `validation_conflict:row_non_compliant` | Any row has `validation.is_compliant == false`. |
| `validation_conflict:suspicious_numeric_values` | Validator emitted a "looks suspicious" deviation. |
| `validation_conflict:heat_number_inconsistency` | Validator flagged a heat-pattern mismatch. |
| `validation_conflict:malformed_numeric_strings` | Separator / formatting issue flagged. |
| `validation_conflict:grade_spec_mismatch` | Grade does not match the extracted mechanical values. |
| `validation_conflict:missing_unit` | Numeric value lacked a clear unit. |
| `row_count_inconsistent` | `total_items_detected != len(items)`. |
| `no_items_extracted` | `len(items) == 0`. |
| `table_found_but_no_rows` | No items AND any page reports `table_detection.table_found == true`. |
| `confidence_below_threshold` | `confidence_score < review_confidence_threshold`. |

Any non-empty token list forces `extraction.needs_review = True` and sets `extraction.status = "NEEDS_REVIEW"` (if it was `COMPLETED`). The original free-form reasons from the validator and confidence normaliser are preserved verbatim.

## 5. Where the route / profile surface in the response

The public `UniversalDocumentExtraction` schema is unchanged. Route, profile, and the structured review decision are stored in the internal `preprocessing_meta` dictionary so they flow into:

- `data/batch_runs/<ts>/per_document/<document_id>.json` (thesis artefact)
- `data/batch_runs/<ts>/summary.csv` (one row per document)
- server logs (INFO-level)

No client-facing change is required for Phase 2.
