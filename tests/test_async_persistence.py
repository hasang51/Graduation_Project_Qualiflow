from __future__ import annotations

from app.services.persistence import persist_analysis_from_extraction_result
from db.models import AnalysisRun, User
from db.session import SessionLocal


def test_persist_analysis_from_extraction_result():
    db = SessionLocal()
    try:
        user = User(email="persist-test@example.com", password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)

        payload = {
            "supplier_name": "Acme Steel",
            "document_type": "MTC",
            "total_items_detected": 1,
            "items": [
                {
                    "item_id": "1",
                    "heat_number": "H123",
                    "grade": "S355J2",
                    "needs_review": False,
                }
            ],
            "confidence_score": 0.91,
            "needs_review": False,
            "status": "COMPLETED",
            "preprocessing_meta": {
                "file_sha256": "deadbeef",
                "page_count": 2,
            },
            "source_filename": "cert.pdf",
        }

        run = persist_analysis_from_extraction_result(
            db,
            user_id=user.id,
            original_filename="cert.pdf",
            stored_pdf_path="uploads/deadbeef/cert.pdf",
            file_sha256="deadbeef",
            result_payload=payload,
        )

        assert isinstance(run, AnalysisRun)
        assert run.user_id == user.id
        assert run.supplier_name == "Acme Steel"
        assert run.status == "COMPLETED"
        assert run.document.stored_pdf_path == "uploads/deadbeef/cert.pdf"
        assert len(run.items) == 1
        assert run.items[0].heat_number == "H123"
    finally:
        db.close()
