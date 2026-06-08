from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    documents: Mapped[list["Document"]] = relationship(back_populates="user")
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="user")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("user_id", "file_sha256", name="uq_user_file_sha256"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(512))
    stored_pdf_path: Mapped[str] = mapped_column(String(1024))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="documents")
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="document")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    global_is_compliant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    certificate_date: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_items_detected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_analysis_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    preprocessing_meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="analysis_runs")
    document: Mapped[Document] = relationship(back_populates="analysis_runs")
    items: Mapped[list["AnalysisItem"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )


class AnalysisItem(Base):
    __tablename__ = "analysis_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    heat_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(255), nullable=True)
    weight_or_length: Mapped[str | None] = mapped_column(String(255), nullable=True)
    yield_strength_mpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    tensile_strength_mpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    elongation_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    row_is_compliant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    deviations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="items")
