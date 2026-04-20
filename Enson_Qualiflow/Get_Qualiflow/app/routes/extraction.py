from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user_optional
from app.models_db import User
from app.schemas.extraction import UniversalDocumentExtraction
from app.services.document_profiler import profile_document
from app.services.extraction_pipeline import run_multi_stage_extraction
from app.services.extraction_router import choose_route
from app.services.persistence import (
    create_processing_run,
    update_run_completed,
    update_run_failed,
    upsert_document,
)
from app.services.preprocessing import preprocess_pdf
from app.services.storage import artifact_dir_for_hash, persist_pdf, sha256_bytes

logger = logging.getLogger("qualiflow.extract")
router = APIRouter(prefix="/api/v1", tags=["extraction"])


@router.post("/extract", response_model=UniversalDocumentExtraction)
async def extract_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    request_filename = file.filename or "document.pdf"
    logger.info("Received extraction request: filename=%s content_type=%s", request_filename, file.content_type)

    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{file.content_type}'. Only PDF files are accepted.",
        )
    if file.filename and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Uploaded file must have a .pdf extension.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_mb} MB limit.")

    file_hash = sha256_bytes(content)
    stored_pdf = persist_pdf(content, file.filename or "document.pdf", file_hash)
    artifact_dir = artifact_dir_for_hash(file_hash)

    preprocessing_meta: dict[str, object] = {
        "file_sha256": file_hash,
        "artifact_dir": str(artifact_dir.resolve()),
        "debug_field_provenance_enabled": settings.debug_field_provenance,
    }
    run = None
    try:
        if current_user:
            document = upsert_document(
                db,
                user=current_user,
                original_filename=file.filename or "document.pdf",
                stored_pdf_path=str(Path(stored_pdf).resolve()),
                file_sha256=file_hash,
                page_count=0,
            )
            run = create_processing_run(
                db,
                user_id=current_user.id,
                document_id=document.id,
                preprocessing_meta=preprocessing_meta,
            )
            db.commit()
            db.refresh(run)

        profile = profile_document(stored_pdf, document_id=file_hash[:16])
        route_decision = choose_route(profile)
        preprocessing_meta["profile"] = profile.to_dict()
        preprocessing_meta["route_decision"] = route_decision.to_dict()
        logger.info(
            "Profiled %s as quality_class=%s selected_route=%s runtime_route=%s",
            request_filename,
            profile.quality_class,
            route_decision.selected_route,
            route_decision.runtime_route,
        )

        processed_pages, pre_meta = preprocess_pdf(
            str(stored_pdf),
            artifact_dir=artifact_dir,
            route=route_decision.runtime_route,
        )
        preprocessing_meta.update(pre_meta)
        logger.info(
            "Preprocessing complete: filename=%s page_count=%s has_table_like_structure=%s route=%s",
            request_filename,
            len(processed_pages),
            any(page.table_crop_available for page in processed_pages),
            route_decision.runtime_route,
        )
        if not processed_pages:
            raise HTTPException(status_code=422, detail="PDF produced zero page images.")

        if current_user and run:
            run = db.get(type(run), run.id)
            if run and run.document:
                run.document.page_count = len(processed_pages)

        extraction = run_multi_stage_extraction(
            processed_pages,
            preprocessing_meta,
            profile=profile,
            route_decision=route_decision,
        )
        logger.info(
            "Extraction complete: filename=%s page_count=%s document_type=%s total_items_detected=%s items_array_length=%s raw_model_confidence=%s confidence_score=%s status=%s",
            request_filename,
            len(processed_pages),
            extraction.document_type,
            extraction.total_items_detected,
            len(extraction.items),
            extraction.raw_model_confidence,
            extraction.confidence_score,
            extraction.status,
        )

        if current_user and run:
            run = db.get(type(run), run.id)
            if run:
                update_run_completed(db, run, extraction, preprocessing_meta)
                db.commit()

        return extraction
    except HTTPException as exc:
        if current_user and run:
            run = db.get(type(run), run.id)
            if run:
                update_run_failed(db, run, exc.detail if isinstance(exc.detail, str) else "Extraction failed.", preprocessing_meta)
                db.commit()
        raise
    except Exception as exc:
        logger.exception("Unhandled extraction error.")
        if current_user and run:
            run = db.get(type(run), run.id)
            if run:
                update_run_failed(db, run, str(exc), preprocessing_meta)
                db.commit()
        raise HTTPException(status_code=502, detail=f"Extraction pipeline failed: {exc}") from exc
