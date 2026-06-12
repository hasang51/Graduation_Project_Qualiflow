# QualiFlow

**A quality-aware hybrid framework for automated extraction and review of industrial CoA/MTC documents**

QualiFlow is an academic research prototype developed as a graduation project. It extracts, normalizes, validates, and reviews structured information from industrial **Certificates of Analysis (CoA)**, **Mill Test Certificates (MTC)**, and related inspection-certificate PDFs.

The system combines multimodal AI extraction with deterministic validation and human-in-the-loop review routing. It is designed to support quality-document verification workflows, not to replace final human approval.

---

## Overview

Industrial quality certificates are often semi-structured, supplier-specific, scanned, noisy, multilingual, or inconsistent across layouts. Critical fields such as heat numbers, batch numbers, material grades, and mechanical properties are frequently embedded in complex tables or degraded PDF scans.

QualiFlow addresses this problem through a hybrid architecture:

* multimodal extraction for document understanding,
* deterministic normalization for critical engineering fields,
* grade/spec validation for supported material families,
* traceability checks for heat, batch, cast, lot, and charge identifiers,
* confidence normalization,
* and structured review-policy decisions.

The project follows a safety-oriented design principle: uncertain cases should be escalated to human review rather than silently approved.

---

## Core Capabilities

QualiFlow extracts and analyzes:

* supplier name,
* document type,
* certificate date,
* item identifiers,
* heat / batch / lot / cast / charge identifiers,
* material grade,
* weight, length, and size descriptors,
* yield strength,
* tensile strength,
* elongation,
* rule-based validation signals,
* traceability status,
* review reasons,
* reviewer focus notes.

The extracted results are returned through a FastAPI backend and displayed in a React frontend.

---

## System Architecture

```text
PDF upload
   │
   ▼
document profiler
   │
   ▼
extraction router
   │
   ▼
preprocessing
   │
   ▼
Claude Stage A: metadata extraction
   │
   ▼
Claude Stage B: line-item extraction
   │
   ▼
normalization and finalization
   │
   ▼
grade/spec validation
   │
   ▼
traceability validation
   │
   ▼
confidence normalization
   │
   ▼
deterministic review policy
   │
   ▼
database persistence + frontend response
```

The runtime pipeline uses a single routed extraction path per document. The public API contract is preserved through the `UniversalDocumentExtraction` response schema, while internal profiling, routing, validation, and review metadata remain available for auditability.

---

## Key Modules

| Area                  | Path                                         | Responsibility                                                |
| --------------------- | -------------------------------------------- | ------------------------------------------------------------- |
| API application       | `app/main.py`                                | FastAPI application entry point                               |
| Extraction route      | `app/routes/extraction.py`                   | PDF upload, profiling, preprocessing, extraction, persistence |
| Document profiler     | `app/services/document_profiler.py`          | PDF quality classification                                    |
| Extraction router     | `app/services/extraction_router.py`          | Route selection based on document profile                     |
| Preprocessing         | `app/services/preprocessing.py`              | Rasterization and image-variant generation                    |
| Extraction pipeline   | `app/services/extraction_pipeline.py`        | Multimodal Stage A/B extraction                               |
| Finalization          | `app/services/extraction_finalizer.py`       | Canonical field cleanup and decision calibration              |
| Identifier extraction | `app/domain/labeled_identifier_extractor.py` | Conservative parsing of labeled traceability identifiers      |
| Grade registry        | `app/domain/grade_registry.py`               | Grade aliasing and canonical grade resolution                 |
| Spec registry         | `app/domain/spec_registry.py`                | Supported deterministic material/spec families                |
| Validator             | `app/services/validator.py`                  | Compliance checks and validation evidence                     |
| Traceability          | `app/services/traceability.py`               | Identifier verification and unsafe-candidate suppression      |
| Review policy         | `app/services/review_policy.py`              | Structured human-review routing                               |
| Frontend              | `frontend/src/`                              | Upload, dashboard, history, and result detail UI              |
| Evaluation            | `scripts/run_eval.py`                        | Live extraction and evaluation workflow                       |
| Metrics               | `scripts/evaluate_outputs.py`                | Re-scoring prediction JSON against gold annotations           |

---

## Technology Stack

### Backend

* Python
* FastAPI
* Pydantic
* SQLAlchemy
* SQLite for local prototype persistence
* Anthropic Claude API for multimodal extraction
* PDF and image preprocessing utilities

### Frontend

* React
* TypeScript
* Vite
* Tailwind CSS

### Evaluation

* Gold-set metadata and ground-truth JSON annotations
* Field-level metrics
* Critical-field metrics
* Quality-bucket metrics
* Failure-case reports

Tesseract is not part of the live runtime pipeline. A legacy offline OCR probe remains in the repository only for reproducibility of earlier cell-level experiments.

---

## Evaluation Results

**Primary evaluation run:** `outputs/eval_runs/live_eval_20260612_1632/`

This run evaluates the current pipeline on a 20-document gold set.

| Metric                       |    Value |
| ---------------------------- | -------: |
| Documents processed          |  20 / 20 |
| Failed PDFs                  |        0 |
| Field Accuracy               |    61.9% |
| Critical Field Accuracy      |    68.8% |
| Document Type Accuracy       |    55.0% |
| Processing Decision Accuracy |    10.0% |
| Review Rate                  |    85.0% |
| Unsafe Auto Accept Rate      |    50.0% |
| Missing Required Field Rate  |     4.5% |
| Average Latency              | 38.8 sec |

### Interpretation

The latest evaluation shows substantial improvement in field extraction and critical-field completeness compared with the earlier baseline. Missing required fields were reduced significantly, and all 20 evaluation documents were processed successfully.

At the same time, the current auto-accept calibration is not production-safe. The unsafe auto-accept rate indicates that some documents requiring review were classified too permissively. Therefore, QualiFlow should be interpreted as a **human-in-the-loop verification assistant**, not as a fully autonomous approval system.

---

## Historical Baseline

The earlier `final20` run is retained as a historical baseline for academic traceability.

| Metric                      | Historical Baseline |
| --------------------------- | ------------------: |
| Field Accuracy              |              14.76% |
| Critical Field Accuracy     |              16.96% |
| Review Rate                 |              100.0% |
| Unsafe Auto Accept Rate     |                0.0% |
| Missing Required Field Rate |               75.0% |

The historical baseline was more conservative but had lower extraction completeness. The latest run improves extraction quality while revealing the need for stricter auto-accept calibration.

---

## Dataset

| Path                                         | Description                     |
| -------------------------------------------- | ------------------------------- |
| `data/eval_docs/`                            | 20 evaluation PDF documents     |
| `data/gold/metadata_20.csv`                  | Metadata index for the gold set |
| `data/gold/ground_truth/`                    | Ground-truth JSON annotations   |
| `outputs/eval_runs/live_eval_20260612_1632/` | Latest evaluation outputs       |
| `outputs/eval_runs/final20/`                 | Historical baseline outputs     |

The evaluation uses exact-match comparison for string fields and tolerance-based comparison for numeric fields. Some formatting-only differences may still be counted as mismatches, such as date separators, Unicode variants, punctuation, supplier-name variants, and spacing differences.

---

## Setup

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Create a repo-root `.env` file based on `.env.example`.

To validate Anthropic authentication without printing the key:

```bash
python -m scripts.check_anthropic_auth
```

### Frontend

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

Set the frontend API base URL in `frontend/.env`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

---

## Demo Flow

1. Start the backend.
2. Start the frontend.
3. Register or log in.
4. Upload a PDF certificate.
5. Review the extracted document summary.
6. Inspect line-item fields and mechanical properties.
7. Check traceability identifiers.
8. Review validation status and review reasons.
9. Open the analysis history page.
10. Inspect the analysis detail page.

---

## API Endpoints

| Method | Endpoint                                   | Description              |
| ------ | ------------------------------------------ | ------------------------ |
| `POST` | `/api/v1/auth/register`                    | Register user            |
| `POST` | `/api/v1/auth/login`                       | Login                    |
| `GET`  | `/api/v1/auth/me`                          | Current user             |
| `POST` | `/api/v1/extract`                          | Upload and analyze a PDF |
| `GET`  | `/api/v1/analyses`                         | List previous analyses   |
| `GET`  | `/api/v1/analyses/{analysis_id}`           | Get analysis detail      |
| `GET`  | `/api/v1/documents/{document_id}/download` | Download source PDF      |
| `GET`  | `/health`                                  | Health check             |

---

## Evaluation Commands

Run live extraction and evaluation:

```bash
python -m scripts.run_eval ^
  --metadata data/gold/metadata_20.csv ^
  --documents-root data/eval_docs ^
  --predictions outputs/eval_runs/live_eval_20260612_1632 ^
  --out outputs/eval_runs/live_eval_20260612_1632
```

Re-score existing predictions without re-running extraction:

```bash
python -m scripts.evaluate_outputs ^
  --metadata data/gold/metadata_20.csv ^
  --predictions outputs/eval_runs/live_eval_20260612_1632 ^
  --out outputs/eval_runs/live_eval_20260612_1632
```

On Unix/macOS shells, replace `^` with `\`.

---

## Tests

Run the full test suite:

```bash
python -m pytest tests/ -q
```

Run targeted traceability and field-mapping tests:

```bash
python -m pytest tests/test_field_mapping_registry.py tests/test_traceability.py -v
```

---

## Known Limitations

* The project is an academic research prototype, not a production SaaS.
* Auto-accept calibration requires further hardening before deployment.
* Severe or degraded scans may still require stricter review gates.
* Deterministic validation is limited to supported grade/spec families.
* Unsupported material families are routed to human review.
* Exact-match evaluation may penalize harmless formatting differences.
* Final certification approval remains a human responsibility.

---

## Documentation

| Document                               | Description                                      |
| -------------------------------------- | ------------------------------------------------ |
| `docs/runtime_architecture.md`         | Runtime architecture and review-token catalogue  |
| `docs/jury_architecture_summary.md`    | Concise architecture summary for academic review |
| `docs/dataset_workflow.md`             | Dataset and evaluation workflow                  |
| `docs/evaluation_protocol.md`          | Evaluation procedure and metric definitions      |
| `docs/review_taxonomy.md`              | Structured review reason taxonomy                |
| `docs/domain_schema.md`                | Domain model and canonical fields                |
| `docs/preprocessing_strategy.md`       | Image preprocessing strategy                     |
| `docs/table_parsing.md`                | Table parsing notes                              |
| `docs/semantic_normalization.md`       | Semantic normalization details                   |
| `docs/QualiFlow_Mimari_Genel_Bakis.md` | Turkish architecture overview                    |

---

## Academic Positioning

QualiFlow demonstrates a safety-aware hybrid approach for industrial quality-document extraction and review. The project shows that multimodal AI can improve field recovery when combined with deterministic validation, traceability checks, and structured human-review routing.

The current prototype is most appropriately positioned as a **quality-document verification assistant**. Its main research value is not only extraction automation, but also the explicit handling of uncertainty, validation limits, and review-required cases.
