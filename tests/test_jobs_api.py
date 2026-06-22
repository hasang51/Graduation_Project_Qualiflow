from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.services.jobs.service import create_queued_job, mark_job_succeeded, store_job_result
from db.session import SessionLocal


def test_job_status_and_result_flow(client: TestClient, minimal_pdf_bytes: bytes):
    with patch("app.api.v1.routes.uploads.enqueue_job", return_value=None):
        upload = client.post(
            "/api/v1/uploads",
            files={"file": ("sample.pdf", minimal_pdf_bytes, "application/pdf")},
        )
    job_id = upload.json()["job_id"]

    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "queued"

    result_resp = client.get(f"/api/v1/jobs/{job_id}/result")
    assert result_resp.status_code == 425

    db = SessionLocal()
    try:
        from app.services.jobs.service import get_job

        job = get_job(db, job_id)
        assert job is not None
        result_key = store_job_result(job_id, {"status": "needs_review", "items": []})
        mark_job_succeeded(db, job, result_key)
    finally:
        db.close()

    done = client.get(f"/api/v1/jobs/{job_id}/result")
    assert done.status_code == 200
    assert done.json()["status"] == "succeeded"
    assert done.json()["result"]["status"] == "needs_review"


def test_job_not_found(client: TestClient):
    assert client.get("/api/v1/jobs/does-not-exist").status_code == 404
