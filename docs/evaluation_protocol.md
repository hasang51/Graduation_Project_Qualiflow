# QualiFlow Evaluation Protocol

This document defines the academic evaluation dataset structure for QualiFlow. It is intentionally separate from the product/runtime flow and does not introduce SaaS behavior, user-facing workflow changes, or new extraction features.

## Dataset Structure

The evaluation dataset is organized under `data/gold/`:

```text
data/gold/
+-- metadata.csv
+-- ground_truth/
    +-- .gitkeep
```

`metadata.csv` is the index for documents selected for academic evaluation. It uses this schema:

```csv
doc_id,file_name,quality_bucket,document_type,pages,has_text_layer,ground_truth_path
```

Each row represents one document in the manually annotated gold subset. `ground_truth_path` should point to the corresponding human-authored annotation file under `data/gold/ground_truth/`.

## Dataset Pool vs Gold Subset

The dataset pool is the broader collection of available Certificates of Analysis and Mill Test Certificates used for discovery, profiling, routing analysis, and candidate selection. The pool may include documents that are not manually annotated and must not be treated as evaluation truth.

The manually annotated gold subset is the smaller set of documents selected from the pool and reviewed by a human annotator. Only this subset can be used for final quantitative evaluation. Model-generated prefill data, dry-run outputs, or provisional extraction results are not gold labels until a human reviewer verifies and corrects them.

## Quality Buckets

Each gold document must be assigned exactly one quality bucket:

- `digital_pdf`: PDF has a usable text layer and clean layout.
- `clean_scan`: Scanned document with readable text, stable table structure, and limited visual degradation.
- `degraded_scan`: Scanned document with blur, noise, compression artifacts, skew, weak contrast, or partially unclear cells.
- `severe_scan`: Document quality is poor enough that key fields or row structure may be unreliable even after preprocessing.

These buckets are evaluation metadata. They should be used for stratified reporting and error analysis, not for changing the product flow.

## Target Fields

The target extraction fields are:

- `supplier_name`
- `document_type`
- `certificate_date`
- `item_id`
- `heat_number`
- `grade`
- `weight_or_length`
- `yield_strength_mpa`
- `tensile_strength_mpa`
- `elongation_percentage`
- `compliance_outcome`
- `review_required`
- `review_reasons`

## Critical Fields

Critical fields are the fields required to support compliance decisions and manual review routing:

- `heat_number`
- `grade`
- `yield_strength_mpa`
- `tensile_strength_mpa`
- `elongation_percentage`
- `compliance_outcome`
- `review_required`

Missing, ambiguous, or incorrectly extracted critical fields must be reported separately from non-critical metadata errors.

## Evaluation Metrics

Evaluation should report both document-level and row-level metrics:

- Field accuracy for all target fields.
- Critical field accuracy for critical fields only.
- Row detection precision, recall, and F1.
- Compliance decision accuracy.
- Review routing accuracy.
- Extraction completeness.
- Quality-bucket breakdowns for each metric.
- Latency and token usage when live model extraction is measured.

Metrics must distinguish final human-verified evaluation from provisional analysis. Results should also include qualitative error categories for unresolved grades, unsupported specs, unreadable scans, row count mismatches, suspicious numeric values, and missing mechanical properties.

## No Fabricated Metrics Policy

No metric may be reported as final unless it is computed from human-verified ground truth annotations in `data/gold/ground_truth/`.

Provisional metrics computed from model-generated prefill files, dry runs, partial live runs, or unverified annotations must be clearly labeled as provisional. They must not be cited as final thesis results, product benchmarks, or validated system performance.

If the gold subset is incomplete, the evaluation report must say so directly and describe the missing annotation work instead of filling gaps with estimated or invented numbers.
