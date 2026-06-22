from __future__ import annotations

from unittest.mock import patch

from app.services.jobs.service import create_queued_job, get_job
from app.workers.tasks import process_document_job
from db.session import SessionLocal


def test_worker_success_path(minimal_pdf_bytes: bytes):
    from app.services.storage.factory import get_storage_backend, reset_storage_backend_cache
    from config.settings import reset_settings_cache

    reset_settings_cache()
    reset_storage_backend_cache()
    db = SessionLocal()
    try:
        from app.services.storage.factory import get_storage_backend

        storage = get_storage_backend()
        key = "uploads/test/worker.pdf"
        storage.put_bytes(key, minimal_pdf_bytes, content_type="application/pdf")
        job = create_queued_job(db, input_object_key=key, original_filename="worker.pdf")
        job_id = job.id
    finally:
        db.close()

    fake_result = {"status": "needs_review", "items": [], "document_type": "MTC"}
    with patch("app.workers.tasks.process_pdf_bytes", return_value=fake_result):
        process_document_job(job_id)

    db = SessionLocal()
    try:
        job = get_job(db, job_id)
        assert job is not None
        assert job.status == "succeeded"
        assert job.result_object_key
    finally:
        db.close()


def test_worker_failure_path(minimal_pdf_bytes: bytes):
    from app.services.storage.factory import reset_storage_backend_cache
    from config.settings import reset_settings_cache

    reset_settings_cache()
    reset_storage_backend_cache()
    db = SessionLocal()
    try:
        from app.services.storage.factory import get_storage_backend

        storage = get_storage_backend()
        key = "uploads/test/fail.pdf"
        storage.put_bytes(key, minimal_pdf_bytes, content_type="application/pdf")
        job = create_queued_job(db, input_object_key=key, original_filename="fail.pdf")
        job_id = job.id
    finally:
        db.close()

    with patch("app.workers.tasks.process_pdf_bytes", side_effect=RuntimeError("boom")):
        try:
            process_document_job(job_id)
        except RuntimeError:
            pass

    db = SessionLocal()
    try:
        job = get_job(db, job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.error_message
    finally:
        db.close()
