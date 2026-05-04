# Methodology

## 3.1 Overview of the Dataset/Model

The QualiFlow project is designed for a heterogeneous manufacturing quality document dataset. The document pool includes industrial quality records such as Certificates of Analysis, Mill Test Certificates, and related material or manufacturing compliance documents. The study therefore does not make a CoA-only claim. Instead, it treats quality documents as a broader class of semi-structured industrial records that may vary in layout, terminology, scan quality, table structure, and availability of embedded text.

The dataset is organized into a broader document pool and a manually annotated gold subset. The broader pool is used for discovery, profiling, routing analysis, and candidate selection. The gold subset is reserved for quantitative evaluation after human annotation. Model-generated prefill files or extraction outputs are not considered ground truth unless they have been manually verified.

The extraction model is used as one component in a controlled pipeline rather than as an unconstrained end-to-end decision system. Claude-based multimodal extraction is responsible for reading document images and returning structured fields. Deterministic components then normalize, validate, and route uncertain outputs to review. This separation is intended to make the system auditable and to reduce dependence on unsupported inference when document evidence is incomplete.

## 3.2 Tools and Technology

The backend is implemented with FastAPI and Python. PDF handling and preprocessing use deterministic document-processing libraries, including PDF rasterization, image analysis, and OpenCV-based transformations. SQLite is used for local persistence in the prototype implementation. The frontend is implemented separately with React and Vite, but the evaluation methodology is independent of the user interface.

The document profiler estimates document quality before extraction. It inspects properties such as page count, presence of an embedded text layer, text density, blur, noise, and table-presence hints. These signals are used to assign a document quality category and provide evidence for later routing and review decisions.

The extraction pipeline uses Claude for structured multimodal extraction. The model is prompted in constrained stages and is expected to return data through predefined schemas rather than free-form prose. The target fields include document-level metadata, row-level identifiers, material grade information, mechanical properties, compliance outcome, and review-related fields.

Post-processing uses deterministic normalization and validation modules. Normalization resolves header variants, field aliases, grade aliases, numeric formats, and row-level semantic inconsistencies. Validation compares extracted values against known material specifications where such deterministic rules are available. Unsupported specification families, unresolved grades, missing critical values, and suspicious numeric ranges are not treated as compliant by assumption; they are routed to review.

## 3.3 Proposed Approach

The proposed approach is a quality-aware hybrid pipeline for manufacturing quality document extraction and verification.

First, each document is profiled before extraction. The profiler assigns a quality bucket based on text-layer availability and visual degradation signals. This step is used to characterize the input and to support later analysis across document quality categories such as digital PDFs, clean scans, degraded scans, and severe scans.

Second, a quality-aware router selects a single extraction route for each document. The router does not run multiple competing extraction systems and does not rely on model arbitration. Instead, it chooses an appropriate path based on the profiler output. This keeps the extraction path explicit and reproducible.

Third, image preprocessing prepares the document for multimodal extraction. Depending on the selected route, preprocessing may include rasterization, grayscale conversion, contrast adjustment, thresholding, table-focused crops, or other deterministic image variants. The objective is to improve readability while preserving document evidence.

Fourth, Claude structured extraction is applied in stages. A metadata stage extracts document-level information such as supplier name, document type, and certificate date. A row extraction stage then extracts table line items and mechanical properties. The model is instructed not to infer unreadable values and to use nulls when evidence is insufficient.

Fifth, normalization converts extracted outputs into canonical project fields. This includes resolving synonymous field labels, normalizing grade expressions, parsing numeric values, propagating supported header context, and preserving provenance where values are derived from document context rather than directly from a row.

Sixth, deterministic validation checks the normalized extraction against available material specification rules. The validation layer supports tri-state outcomes. A row may be compliant, non-compliant, or unresolved/needs review. Unknown grades, unsupported specification families, missing critical fields, and ambiguous evidence are not converted into final compliance decisions without review.

Seventh, confidence scoring and the human review policy determine whether a document can be auto-accepted or must be reviewed. The review policy considers document quality, missing critical fields, blocking validation errors, unsupported document types, and critical-field confidence. Missing critical values are never auto-filled. Severe scans and unsupported document types cannot be auto-accepted.

Finally, evaluation is performed against manually verified ground truth. The planned metrics include field accuracy, critical field accuracy, document type accuracy, processing decision accuracy, review rate, unsafe auto-accept rate, missing required field rate, and average latency when latency is present in prediction files. Metrics should also be reported by quality bucket and by field. At the time this methodology document is written, no final metric claim is made unless corresponding evaluation output files exist and are computed from human-verified gold annotations.
