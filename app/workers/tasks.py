from __future__ import annotations

import logging

from db.session import SessionLocal
from app.services.document_processor import process_pdf_bytes
from app.services.jobs.service import (
    get_job,
    mark_job_failed,
    mark_job_processing,
    mark_job_succeeded,
    store_job_result,
)
from app.services.storage.factory import get_storage_backend
from app.observability.metrics import record_worker_failure, record_worker_success

logger = logging.getLogger("qualiflow.worker")


def process_document_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = get_job(db, job_id)
        if job is None:
            logger.error("Job not found: %s", job_id)
            return
        if job.status in {"succeeded", "failed", "cancelled"}:
            logger.info("Job %s already terminal (%s); skipping.", job_id, job.status)
            return

        mark_job_processing(db, job)
        logger.info("Processing job %s trace_id=%s", job_id, job.trace_id)

        storage = get_storage_backend()
        pdf_bytes = storage.get_bytes(job.input_object_key)
        result_payload = process_pdf_bytes(pdf_bytes, filename=job.original_filename)
        result_key = store_job_result(job_id, result_payload)
        mark_job_succeeded(db, job, result_key)
        record_worker_success()
        logger.info("Job %s succeeded result_key=%s", job_id, result_key)
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        record_worker_failure()
        try:
            job = get_job(db, job_id)
            if job is not None:
                mark_job_failed(db, job, "Document processing failed.")
        except Exception:
            logger.exception("Failed to mark job %s as failed", job_id)
        raise exc
    finally:
        db.close()
