from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models_db import AnalysisRun, Document, User
from app.schemas.analysis import AnalysisDetail, AnalysisListItem
from app.schemas.extraction import UniversalDocumentExtraction
from app.services.traceability import sanitize_result_for_api_boundary

router = APIRouter(prefix="/api/v1", tags=["analyses"])


@router.get("/analyses", response_model=list[AnalysisListItem])
def list_analyses(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(AnalysisRun).where(AnalysisRun.user_id == current_user.id).order_by(desc(AnalysisRun.created_at))
    ).all()
    return [
        AnalysisListItem(
            id=row.id,
            document_id=row.document_id,
            status=row.status,
            extraction_confidence=row.extraction_confidence,
            global_is_compliant=row.global_is_compliant,
            supplier_name=row.supplier_name,
            document_type=row.document_type,
            total_items_detected=row.total_items_detected,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get("/analyses/{analysis_id}", response_model=AnalysisDetail)
def get_analysis(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(AnalysisRun, analysis_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    extraction = None
    raw_json = json.loads(row.raw_response_json) if row.raw_response_json else None
    if isinstance(raw_json, dict):
        raw_json = sanitize_result_for_api_boundary(raw_json)
    pre_meta = json.loads(row.preprocessing_meta_json) if row.preprocessing_meta_json else None
    if raw_json:
        extraction = UniversalDocumentExtraction.model_validate(raw_json)

    return AnalysisDetail(
        id=row.id,
        document_id=row.document_id,
        status=row.status,
        extraction_confidence=row.extraction_confidence,
        global_is_compliant=row.global_is_compliant,
        supplier_name=row.supplier_name,
        document_type=row.document_type,
        certificate_date=row.certificate_date,
        total_items_detected=row.total_items_detected,
        ai_analysis_remarks=row.ai_analysis_remarks,
        raw_response_json=raw_json,
        preprocessing_meta_json=pre_meta,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
        extraction=extraction,
    )


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if doc is None or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found.")
    file_path = Path(doc.stored_pdf_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Stored PDF file not found.")
    return FileResponse(path=file_path, filename=doc.original_filename, media_type="application/pdf")
