from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.extraction import UniversalDocumentExtraction


class AnalysisListItem(BaseModel):
    id: int
    document_id: int
    status: str
    extraction_confidence: float | None
    global_is_compliant: bool | None
    supplier_name: str | None
    document_type: str | None
    total_items_detected: int | None
    created_at: datetime
    updated_at: datetime


class AnalysisDetail(BaseModel):
    id: int
    document_id: int
    status: str
    extraction_confidence: float | None
    global_is_compliant: bool | None
    supplier_name: str | None
    document_type: str | None
    certificate_date: str | None
    total_items_detected: int | None
    ai_analysis_remarks: str | None
    raw_response_json: dict[str, Any] | None
    preprocessing_meta_json: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    extraction: UniversalDocumentExtraction | None
