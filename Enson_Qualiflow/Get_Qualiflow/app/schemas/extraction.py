from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MechanicalProperties(BaseModel):
    yield_strength_mpa: Optional[float] = Field(default=None)
    tensile_strength_mpa: Optional[float] = Field(default=None)
    elongation_percentage: Optional[float] = Field(default=None)


class ValidationResult(BaseModel):
    """Outcome of validating a single row.

    ``is_compliant`` is tri-state:

    - ``True``  => resolved & compliant,
    - ``False`` => resolved & non-compliant,
    - ``None``  => unresolved / not applicable / extraction uncertain.

    ``outcome`` is the narrow machine-readable tag the frontend uses to
    pick a badge.
    """

    is_compliant: Optional[bool] = Field(default=True)
    deviations: List[str] = Field(default_factory=list)
    outcome: Optional[str] = Field(default=None)


class ExtractedItem(BaseModel):
    item_id: Optional[str] = Field(default=None)
    heat_number: Optional[str] = Field(default=None)
    grade: Optional[str] = Field(default=None)
    weight_or_length: Optional[str] = Field(default=None)
    mechanical_properties: Optional[MechanicalProperties] = Field(default=None)
    validation: Optional[ValidationResult] = Field(default=None)
    row_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    needs_review: bool = Field(default=False)
    # Phase 1 additions (all optional to keep API shape backward-compatible)
    grade_resolution: Optional[Dict[str, Any]] = Field(default=None)
    grade_provenance: Optional[str] = Field(default=None)


class UniversalDocumentExtraction(BaseModel):
    supplier_name: str = Field(...)
    document_type: str = Field(...)
    certificate_date: Optional[str] = Field(default=None)
    total_items_detected: int = Field(...)
    items: List[ExtractedItem] = Field(...)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    raw_model_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ai_analysis_remarks: Optional[str] = Field(default=None)
    is_compliant: Optional[bool] = Field(default=None)
    status: Optional[str] = Field(default=None)
    needs_review: bool = Field(default=False)
    review_reasons: List[str] = Field(default_factory=list)
