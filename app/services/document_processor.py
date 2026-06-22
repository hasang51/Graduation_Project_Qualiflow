from __future__ import annotations

import hashlib
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.document_profiler import profile_document
from app.services.extraction_pipeline import run_multi_stage_extraction
from app.services.extraction_router import choose_route
from app.services.preprocessing import preprocess_pdf
from app.services.storage import artifact_dir_for_hash
from app.services.traceability import sanitize_result_for_api_boundary, sanitize_unverified_traceability_for_user

logger = logging.getLogger("qualiflow.processor")

_REMARK_SUPPRESSED_PHRASE_PATTERN = re.compile(
    r"secondary\s+identifier\s+candidates?|"
    r"candidate\s+identifier|"
    r"\bitem\s*id\b|"
    r"\bpipe\s*coil\s*id\b",
    re.IGNORECASE,
)


def _sanitize_ai_analysis_remarks_for_presentation(remarks: str | None) -> str | None:
    if remarks is None:
        return None
    text = remarks.strip()
    if not text:
        return None
    kept_lines: list[str] = []
    for raw_line in re.split(r"\r?\n", text):
        line = raw_line.strip()
        if not line:
            continue
        segments = re.split(r"(?<=\.)\s+", line)
        kept_segments = [
            segment.strip()
            for segment in segments
            if segment.strip() and not _REMARK_SUPPRESSED_PHRASE_PATTERN.search(segment)
        ]
        if kept_segments:
            kept_lines.append(" ".join(kept_segments))
    sanitized = "\n".join(kept_lines).strip()
    return sanitized or None


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_pdf_upload(content: bytes, content_type: str | None, filename: str | None) -> None:
    from fastapi import HTTPException

    if content_type and content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{content_type}'. Only PDF files are accepted.",
        )
    if filename and not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Uploaded file must have a .pdf extension.")
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=415, detail="File does not appear to be a valid PDF.")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_mb} MB limit.")


def process_pdf_bytes(content: bytes, *, filename: str = "document.pdf") -> dict[str, Any]:
    """Run the full extraction pipeline on PDF bytes and return API-safe payload."""
    file_hash = sha256_bytes(content)
    with tempfile.TemporaryDirectory(prefix="qualiflow_") as tmpdir:
        tmp_path = Path(tmpdir) / "input.pdf"
        tmp_path.write_bytes(content)
        artifact_dir = artifact_dir_for_hash(file_hash)

        preprocessing_meta: dict[str, object] = {
            "file_sha256": file_hash,
            "artifact_dir": str(artifact_dir.resolve()),
            "debug_field_provenance_enabled": settings.debug_field_provenance,
        }

        profile = profile_document(str(tmp_path), document_id=file_hash[:16])
        route_decision = choose_route(profile)
        preprocessing_meta["profile"] = profile.to_dict()
        preprocessing_meta["route_decision"] = route_decision.to_dict()

        processed_pages, pre_meta = preprocess_pdf(
            str(tmp_path),
            artifact_dir=artifact_dir,
            route=route_decision.runtime_route,
        )
        preprocessing_meta.update(pre_meta)
        if not processed_pages:
            raise ValueError("PDF produced zero page images.")

        extraction = run_multi_stage_extraction(
            processed_pages,
            preprocessing_meta,
            profile=profile,
            route_decision=route_decision,
        )
        sanitize_unverified_traceability_for_user(extraction)
        if extraction.review_reasons and any(
            reason in {"traceability_unverified", "critical_identifier_unverified"}
            for reason in extraction.review_reasons
        ):
            extraction.ai_analysis_remarks = (
                "Mechanical values were extracted, but traceability-critical identifiers could not be "
                "verified with production-grade confidence. The system intentionally suppresses "
                "ambiguous identifier candidates and routes the affected rows to human review."
            )

        payload = sanitize_result_for_api_boundary(extraction)
        payload["ai_analysis_remarks"] = _sanitize_ai_analysis_remarks_for_presentation(
            payload.get("ai_analysis_remarks")
        )
        payload["preprocessing_meta"] = preprocessing_meta
        payload["source_filename"] = filename
        return payload
