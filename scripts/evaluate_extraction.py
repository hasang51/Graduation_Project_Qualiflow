from __future__ import annotations

import json
from pathlib import Path

import requests

from app.domain.validation_config import DEFAULT_TENSILE_RANGE, DEFAULT_YIELD_RANGE

BASE_URL = "http://127.0.0.1:8000"
FILES = ["belge.pdf", "noisy_image.pdf"]
OUTPUT_DIR = Path("data/outputs")


def run_extract(pdf_path: Path) -> dict:
    with pdf_path.open("rb") as file_stream:
        response = requests.post(
            f"{BASE_URL}/api/v1/extract",
            files={"file": (pdf_path.name, file_stream, "application/pdf")},
            timeout=240,
        )
    response.raise_for_status()
    return response.json()


def summarize(data: dict) -> dict:
    items = data.get("items", [])
    missing_yield = sum(1 for row in items if not (row.get("mechanical_properties") or {}).get("yield_strength_mpa"))
    suspicious = 0
    for row in items:
        mp = row.get("mechanical_properties") or {}
        y = mp.get("yield_strength_mpa")
        t = mp.get("tensile_strength_mpa")
        if isinstance(y, (int, float)) and DEFAULT_YIELD_RANGE.is_suspicious(float(y)):
            suspicious += 1
        if isinstance(t, (int, float)) and DEFAULT_TENSILE_RANGE.is_suspicious(float(t)):
            suspicious += 1
    return {
        "row_count": len(items),
        "confidence": data.get("confidence_score"),
        "needs_review": data.get("needs_review"),
        "missing_yield_values": missing_yield,
        "suspicious_numeric_mismatches": suspicious,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        path = Path(name)
        if not path.exists():
            print(f"[SKIP] {name} not found.")
            continue
        print(f"[RUN] {name}")
        payload = run_extract(path)
        (OUTPUT_DIR / f"{path.stem}_result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(summarize(payload), indent=2))


if __name__ == "__main__":
    main()
