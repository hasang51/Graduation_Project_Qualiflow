# QualiFlow

Academic research prototype for quality-aware hybrid CoA/MTC verification.

---

## A. Project Overview

QualiFlow is a **graduation-project research prototype**, not a productised SaaS. It ingests industrial **Certificates of Analysis (CoA)**, **Mill Test Certificates (MTC)**, and related inspection-certificate PDFs, then extracts:

- document metadata and traceability identifiers,
- mechanical properties and line-item fields,
- compliance-related signals used for deterministic validation and review routing.

The system combines **Claude multimodal extraction**, **deterministic grade/spec validation**, and an **auditable review policy** that separates validation outcomes from automation decisions.

**Tesseract is not part of the runtime.** A legacy offline OCR probe (`scripts/check_ocr_backend.py`) remains in the repository for reproducibility of earlier cell-level experiments only; the live pipeline does not import or call it.

Further architecture detail: [docs/runtime_architecture.md](docs/runtime_architecture.md) · [docs/jury_architecture_summary.md](docs/jury_architecture_summary.md)

---

## B. Architecture

End-to-end processing flow:

```
PDF upload
   │
   ▼
document profiler              (app/services/document_profiler.py)
   │  quality_class ∈ {digital_clean, scan_clean, noisy_scan, severe_scan}
   ▼
extraction router              (app/services/extraction_router.py)
   │  exactly one route per document
   ▼
preprocessing                  (app/services/preprocessing.py)
   │  route-driven rasterisation and image variants
   ▼
Claude Stage A                 metadata extraction
   ▼
Claude Stage B                 line-item extraction
   ▼
normalization / finalization   (app/services/extraction_finalizer.py, semantic normalizers)
   ▼
grade / spec validation        (app/services/validator.py, app/domain/grade_registry.py, app/domain/spec_registry.py)
   ▼
traceability validation        (app/services/traceability.py)
   ▼
confidence normalization       (app/services/confidence.py)
   ▼
deterministic review policy    (app/services/review_policy.py)
   ▼
persistence + UI response      (FastAPI + React frontend)
```

The public API contract (`POST /api/v1/extract`, `UniversalDocumentExtraction` schema) is preserved. Route, profile, and review metadata are stored in internal `preprocessing_meta` for inspection without breaking the outward contract.

---

## C. Key Modules

| Module | Path | Role |
| --- | --- | --- |
| Document profiler | `app/services/document_profiler.py` | Classifies PDF quality from text layer, blur, and noise signals |
| Extraction router | `app/services/extraction_router.py` | Selects exactly one extraction route per document |
| Preprocessing | `app/services/preprocessing.py` | Rasterises pages and builds route-aware image variants |
| Extraction pipeline | `app/services/extraction_pipeline.py` | Claude Stage A/B tool-use extraction and orchestration |
| Extraction finalizer | `app/services/extraction_finalizer.py` | Canonical field finalization and decision tokens |
| Labeled identifier extractor | `app/domain/labeled_identifier_extractor.py` | Parses labeled traceability identifiers from headers |
| Grade registry | `app/domain/grade_registry.py` | Known steel-grade aliases and normalization |
| Spec registry | `app/domain/spec_registry.py` | Supported material/spec families for deterministic checks |
| Validator | `app/services/validator.py` | Grade-aware compliance, suspicious numerics, heat-pattern checks |
| Review policy | `app/services/review_policy.py` | Structured, auditable review reason tokens |
| Frontend UI | `frontend/src/` | Upload, results, history, and analysis detail pages |
| Evaluation runner | `scripts/run_eval.py` | Live extraction + gold-set evaluation harness |
| Evaluation metrics | `scripts/evaluate_outputs.py` | Re-score existing prediction JSON against gold annotations |

---

## D. Latest Evaluation Results

**Primary reference run:** [`outputs/eval_runs/live_eval_20260612_1632/`](outputs/eval_runs/live_eval_20260612_1632/)

| Metric | Value |
| --- | --- |
| Documents processed | 20 / 20 |
| Failed PDFs | 0 |
| Field Accuracy | 61.9% |
| Critical Field Accuracy | 68.8% |
| Document Type Accuracy | 55.0% |
| Processing Decision Accuracy | 10.0% |
| Review Rate | 85.0% |
| Unsafe Auto Accept Rate | 50.0% |
| Missing Required Field Rate | 4.5% |
| Average Latency | 38.8 sec |

**Interpretation:** Compared with the earlier preliminary `final20` run, field extraction and missing-field completeness improved substantially. However, **unsafe auto-accept remains a known limitation**, especially for difficult or severe scans. The prototype should therefore be interpreted as a **human-in-the-loop verification assistant**, not a fully autonomous certification authority.

Artifacts for this run:

- Summary: [`metrics_summary.md`](outputs/eval_runs/live_eval_20260612_1632/metrics_summary.md)
- Report: [`eval_report.md`](outputs/eval_runs/live_eval_20260612_1632/eval_report.md)
- Predictions: `outputs/eval_runs/live_eval_20260612_1632/doc001.json` … `doc020.json`
- Gold annotations: [`data/gold/ground_truth/`](data/gold/ground_truth/)
- Metadata index: [`data/gold/metadata_20.csv`](data/gold/metadata_20.csv)

---

## E. Historical Evaluation

**Preliminary / historical baseline:** [`outputs/eval_runs/final20/`](outputs/eval_runs/final20/)

This run reflects an **older pipeline state** before the latest extraction and finalization improvements. It is retained for academic traceability only.

| Metric | Value |
| --- | --- |
| Field Accuracy | 14.76% |
| Critical Field Accuracy | 16.96% |
| Review Rate | 100% |
| Unsafe Auto Accept Rate | 0% |
| Missing Required Field Rate | 75% |

Report: [`outputs/eval_runs/final20/eval_report.md`](outputs/eval_runs/final20/eval_report.md)

---

## F. Known Limitations

- **Not production SaaS.** Security, deployment, and operational hardening are prototype-level.
- **Auto-accept calibration is not production-safe.** The latest run shows a 50% unsafe auto-accept rate on gold review-required documents.
- **Severe scans** still need stricter review gates; quality class alone is diagnostic, not a standalone blocker.
- **Exact-match evaluation** may penalize harmless formatting differences (date separators, Unicode variants, punctuation, supplier-name variants).
- **Deterministic validation** covers only supported grade/spec families; unsupported material families route to human review.
- **Final approval remains a human responsibility.** The system assists extraction and compliance checking; it does not replace a certification authority.

---

## G. Setup / Run

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Configure API keys in a repo-root `.env` file (see `.env.example`). Never commit secrets.

Validate Anthropic credentials without printing the key:

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

Open `http://127.0.0.1:5173`. Set `VITE_API_BASE_URL=http://127.0.0.1:8000` in `frontend/.env`.

**Demo flow:** Register → Log in → Upload PDF → Inspect results → History → Detail page → Download source PDF.

### API endpoints

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET  /api/v1/auth/me`
- `POST /api/v1/extract`
- `GET  /api/v1/analyses`
- `GET  /api/v1/analyses/{analysis_id}`
- `GET  /api/v1/documents/{document_id}/download`
- `GET  /health`

---

## H. Evaluation Commands

Full live re-run over the 20-document gold set (requires Anthropic API access and PDFs under `data/eval_docs/`):

```bash
python -m scripts.run_eval ^
  --metadata data/gold/metadata_20.csv ^
  --documents-root data/eval_docs ^
  --predictions outputs/eval_runs/live_eval_20260612_1632 ^
  --out outputs/eval_runs/live_eval_20260612_1632
```

Re-score **existing** prediction JSON without re-extracting:

```bash
python -m scripts.evaluate_outputs ^
  --metadata data/gold/metadata_20.csv ^
  --predictions outputs/eval_runs/live_eval_20260612_1632 ^
  --out outputs/eval_runs/live_eval_20260612_1632
```

On Unix shells, replace `^` with `\`.

See also [docs/evaluation_protocol.md](docs/evaluation_protocol.md) and [docs/dataset_workflow.md](docs/dataset_workflow.md).

---

## I. Repository Contents for ZIP Submission

### Include

| Path | Notes |
| --- | --- |
| `app/` | Backend source |
| `frontend/src/` | React UI source |
| `frontend/package.json`, `frontend/package-lock.json` | Frontend dependencies |
| `scripts/` | Batch, evaluation, and utility scripts |
| `tests/` | Unit and regression tests |
| `docs/` | Architecture and methodology notes |
| `data/gold/` | Gold metadata and ground-truth JSON |
| `data/eval_docs/` | Evaluation PDF dataset (20 documents) |
| `outputs/eval_runs/live_eval_20260612_1632/` | Latest primary evaluation run |
| `outputs/eval_runs/final20/` | Historical preliminary baseline |
| `README.md`, `requirements.txt`, `.env.example` | Project entry points |

See [SUBMISSION_MANIFEST.md](SUBMISSION_MANIFEST.md) for the full delivery checklist.

### Exclude

- `.env`, API keys, and any secret files
- `.venv/`, `node_modules/`
- `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`
- `dist/`, `build/`, `frontend/dist/`
- `data/qualiflow.db` (local SQLite runtime database)
- `data/storage/` (uploaded PDFs and preprocessing artifacts)
- Debug and runtime logs (`debug-*.log`, `*.log`)
- Local IDE folders (`.vscode/`, `.idea/`)
- Personal machine paths and ephemeral development outputs

---

## Tests

```bash
python -m pytest tests/ -q
```

Targeted suites:

```bash
python -m pytest tests/test_field_mapping_registry.py tests/test_traceability.py -v
```

Install dependencies from `requirements.txt` before running the full suite.

---

## Additional Documentation

- [docs/runtime_architecture.md](docs/runtime_architecture.md) — profiler heuristics, router table, review-token catalogue
- [docs/dataset_workflow.md](docs/dataset_workflow.md) — manifest, gold-candidate, and batch workflow
- [docs/review_taxonomy.md](docs/review_taxonomy.md) — structured review reason tokens
- [docs/QualiFlow_Mimari_Genel_Bakis.md](docs/QualiFlow_Mimari_Genel_Bakis.md) — architecture overview (Turkish)
