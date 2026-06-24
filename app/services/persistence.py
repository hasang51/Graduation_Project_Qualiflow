from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models_db import AnalysisItem, AnalysisRun, Document, User
from app.schemas.extraction import UniversalDocumentExtraction
from app.services.traceability import sanitize_result_for_api_boundary, sanitize_unverified_traceability_for_user

_RESULT_META_KEYS = frozenset({"preprocessing_meta", "source_filename"})


def upsert_document(
    db: Session,
    *,
    user: User,
    original_filename: str,
    stored_pdf_path: str,
    file_sha256: str,
    page_count: int,
) -> Document:
    existing = db.scalar(select(Document).where(Document.user_id == user.id, Document.file_sha256 == file_sha256))
    if existing:
        return existing
    doc = Document(
        user_id=user.id,
        original_filename=original_filename,
        stored_pdf_path=stored_pdf_path,
        file_sha256=file_sha256,
        page_count=page_count,
    )
    db.add(doc)
    db.flush()
    return doc


def create_processing_run(
    db: Session,
    *,
    user_id: int,
    document_id: int,
    preprocessing_meta: dict[str, Any],
) -> AnalysisRun:
    run = AnalysisRun(
        user_id=user_id,
        document_id=document_id,
        status="PROCESSING",
        preprocessing_meta_json=json.dumps(preprocessing_meta, ensure_ascii=False),
    )
    db.add(run)
    db.flush()
    return run


def update_run_completed(
    db: Session,
    run: AnalysisRun,
    extraction: UniversalDocumentExtraction,
    preprocessing_meta: dict[str, Any],
) -> AnalysisRun:
    sanitize_unverified_traceability_for_user(extraction)
    sanitized_payload = sanitize_result_for_api_boundary(extraction)

    run.status = extraction.status or ("NEEDS_REVIEW" if extraction.needs_review else "COMPLETED")
    run.extraction_confidence = extraction.confidence_score
    run.global_is_compliant = extraction.is_compliant
    run.supplier_name = extraction.supplier_name
    run.document_type = extraction.document_type
    run.certificate_date = extraction.certificate_date
    run.total_items_detected = extraction.total_items_detected
    run.ai_analysis_remarks = extraction.ai_analysis_remarks
    run.raw_response_json = json.dumps(sanitized_payload, ensure_ascii=False)
    run.preprocessing_meta_json = json.dumps(preprocessing_meta, ensure_ascii=False)
    run.error_message = None

    db.query(AnalysisItem).filter(AnalysisItem.analysis_run_id == run.id).delete()
    for idx, item in enumerate(extraction.items):
        deviations = item.validation.deviations if item.validation else []
        row = AnalysisItem(
            analysis_run_id=run.id,
            row_index=idx,
            item_id=item.item_id,
            heat_number=item.heat_number,
            grade=item.grade,
            weight_or_length=item.weight_or_length,
            yield_strength_mpa=item.mechanical_properties.yield_strength_mpa if item.mechanical_properties else None,
            tensile_strength_mpa=item.mechanical_properties.tensile_strength_mpa if item.mechanical_properties else None,
            elongation_percentage=item.mechanical_properties.elongation_percentage if item.mechanical_properties else None,
            row_is_compliant=item.validation.is_compliant if item.validation else None,
            deviations_json=json.dumps(deviations, ensure_ascii=False),
            row_confidence=item.row_confidence,
            needs_review=item.needs_review,
        )
        db.add(row)
    db.flush()
    return run


def update_run_failed(db: Session, run: AnalysisRun, error_message: str, preprocessing_meta: dict[str, Any]) -> AnalysisRun:
    run.status = "FAILED"
    run.error_message = error_message
    run.preprocessing_meta_json = json.dumps(preprocessing_meta, ensure_ascii=False)
    db.flush()
    return run


def begin_analysis_for_user(
    db: Session,
    *,
    user: User,
    original_filename: str,
    stored_pdf_path: str,
    file_sha256: str,
    preprocessing_meta: dict[str, Any],
    page_count: int = 0,
) -> AnalysisRun:
    """Create or reuse a document row and open an analysis run (sync upload path)."""
    document = upsert_document(
        db,
        user=user,
        original_filename=original_filename,
        stored_pdf_path=stored_pdf_path,
        file_sha256=file_sha256,
        page_count=page_count,
    )
    return create_processing_run(
        db,
        user_id=user.id,
        document_id=document.id,
        preprocessing_meta=preprocessing_meta,
    )


def extraction_payload_from_result(result_payload: dict[str, Any]) -> tuple[UniversalDocumentExtraction, dict[str, Any]]:
    preprocessing_meta = result_payload.get("preprocessing_meta")
    if not isinstance(preprocessing_meta, dict):
        preprocessing_meta = {}
    extraction_data = {key: value for key, value in result_payload.items() if key not in _RESULT_META_KEYS}
    extraction = UniversalDocumentExtraction.model_validate(extraction_data)
    return extraction, preprocessing_meta


def _page_count_from_preprocessing_meta(preprocessing_meta: dict[str, Any]) -> int:
    page_count = preprocessing_meta.get("page_count")
    if isinstance(page_count, int) and page_count >= 0:
        return page_count
    profile = preprocessing_meta.get("profile")
    if isinstance(profile, dict):
        raw = profile.get("page_count")
        if isinstance(raw, int) and raw >= 0:
            return raw
    return 0


def persist_analysis_from_extraction_result(
    db: Session,
    *,
    user_id: int,
    original_filename: str,
    stored_pdf_path: str,
    file_sha256: str,
    result_payload: dict[str, Any],
) -> AnalysisRun:
    """Persist a completed extraction for async worker jobs (authenticated users only)."""
    user = db.get(User, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found.")

    extraction, preprocessing_meta = extraction_payload_from_result(result_payload)
    page_count = _page_count_from_preprocessing_meta(preprocessing_meta)

    document = upsert_document(
        db,
        user=user,
        original_filename=original_filename,
        stored_pdf_path=stored_pdf_path,
        file_sha256=file_sha256,
        page_count=page_count,
    )
    run = create_processing_run(
        db,
        user_id=user.id,
        document_id=document.id,
        preprocessing_meta=preprocessing_meta,
    )
    update_run_completed(db, run, extraction, preprocessing_meta)
    db.commit()
    db.refresh(run)
    return run
