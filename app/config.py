from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _load_env_files() -> list[str]:
    """Load env from the repo root first, then ``docs/.env`` as a fallback.

    The second call does NOT override values already present in the process
    environment (``override=False``), so a real root ``.env`` always wins over
    a stale fallback. The helper returns the list of files it actually loaded
    for diagnostics — call sites must not print secret values.
    """

    repo_root = Path(__file__).resolve().parent.parent
    loaded: list[str] = []

    root_env = repo_root / ".env"
    if root_env.exists():
        load_dotenv(root_env, override=False)
        loaded.append(str(root_env.name))

    docs_env = repo_root / "docs" / ".env"
    if docs_env.exists():
        load_dotenv(docs_env, override=False)
        loaded.append(f"docs/{docs_env.name}")

    # Also pick up any ``.env`` in CWD via the default behaviour (useful when
    # the user runs scripts from a sibling folder).
    load_dotenv(override=False)
    return loaded


ENV_FILES_LOADED = _load_env_files()


class Settings:
    def __init__(self) -> None:
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self.pdf_dpi = int(os.getenv("PDF_DPI", "400"))
        self.poppler_path = os.getenv("POPPLER_PATH", r"C:\poppler\Library\bin")
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./data/qualiflow.db")
        self.storage_dir = Path(os.getenv("STORAGE_DIR", "./data/storage"))
        self.jwt_secret_key = os.getenv("JWT_SECRET_KEY", "change-me")
        self.access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "240"))
        self.review_confidence_threshold = float(os.getenv("REVIEW_CONFIDENCE_THRESHOLD", "0.75"))
        self.max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "20"))
        self.max_pages_for_llm = int(os.getenv("MAX_PAGES_FOR_LLM", "8"))
        self.llm_image_max_edge = int(os.getenv("LLM_IMAGE_MAX_EDGE", "1600"))
        self.llm_image_target_bytes = int(os.getenv("LLM_IMAGE_TARGET_BYTES", "4500000"))
        self.llm_image_min_edge = int(os.getenv("LLM_IMAGE_MIN_EDGE", "900"))
        self.llm_jpeg_quality = int(os.getenv("LLM_JPEG_QUALITY", "82"))
        # OCR settings below are consumed ONLY by the offline legacy probe
        # (scripts/check_ocr_backend.py and app/services/ocr_service.py). The
        # main extraction runtime never reads them.
        self.ocr_backend = os.getenv("OCR_BACKEND", "pytesseract").strip().lower() or "pytesseract"
        self.tesseract_cmd = os.getenv("TESSERACT_CMD", "").strip()
        self.ocr_fail_loudly = os.getenv("OCR_FAIL_LOUDLY", "0").strip().lower() in {"1", "true", "yes", "on"}
        self.debug_field_provenance = os.getenv("DEBUG_FIELD_PROVENANCE", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
