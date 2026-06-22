"""Deterministic text normalization for evaluation matching."""

from __future__ import annotations

import re
import unicodedata

# Greek letters commonly confused with Latin in supplier OCR.
_GREEK_TO_LATIN = str.maketrans(
    {
        "\u0391": "A",
        "\u0392": "B",
        "\u0395": "E",
        "\u0397": "H",
        "\u0399": "I",
        "\u039a": "K",
        "\u039c": "M",
        "\u039d": "N",
        "\u039f": "O",
        "\u03a1": "P",
        "\u03a4": "T",
        "\u03a7": "X",
        "\u03a5": "Y",
        "\u0396": "Z",
        "\u03b1": "a",
        "\u03b2": "b",
        "\u03b5": "e",
        "\u03b7": "h",
        "\u03b9": "i",
        "\u03ba": "k",
        "\u03bc": "m",
        "\u03bd": "n",
        "\u03bf": "o",
        "\u03c1": "p",
        "\u03c4": "t",
        "\u03c7": "x",
        "\u03c5": "y",
        "\u03b6": "z",
    }
)

_SAFE_PUNCT_RE = re.compile(r"[^\w\s./\-+]", re.UNICODE)
_COLLAPSE_WS_RE = re.compile(r"\s+")

_SUPPLIER_SUFFIX_REPLACEMENTS = (
    (re.compile(r"\bs\.?\s*p\.?\s*a\.?\b", re.IGNORECASE), " spa "),
    (re.compile(r"\bs\.?\s*r\.?\s*l\.?\b", re.IGNORECASE), " srl "),
    (re.compile(r"\bltd\.?\b", re.IGNORECASE), " ltd "),
    (re.compile(r"\binc\.?\b", re.IGNORECASE), " inc "),
    (re.compile(r"\bcorp\.?\b", re.IGNORECASE), " corp "),
    (re.compile(r"\bgmbh\b", re.IGNORECASE), " gmbh "),
    (re.compile(r"\bco\.?\b", re.IGNORECASE), " co "),
)


def is_missing(value: object | None) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def to_raw_string(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "|".join(to_raw_string(v) for v in value)
    return str(value)


def normalize_exact(value: object | None) -> str:
    """NFKC, strip, collapse whitespace, safe punctuation, lowercase."""
    text = to_raw_string(value)
    text = unicodedata.normalize("NFKC", text).strip()
    text = _SAFE_PUNCT_RE.sub(" ", text)
    text = _COLLAPSE_WS_RE.sub(" ", text)
    return text.lower()


def normalize_critical_identifier(value: object | None) -> str:
    """Minimal normalization: outer whitespace trim only."""
    return to_raw_string(value).strip()


def normalize_supplier_name(value: object | None) -> str:
    text = unicodedata.normalize("NFKC", to_raw_string(value)).translate(_GREEK_TO_LATIN)
    text = text.strip()
    for pattern, replacement in _SUPPLIER_SUFFIX_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    text = _SAFE_PUNCT_RE.sub(" ", text)
    text = _COLLAPSE_WS_RE.sub(" ", text)
    return text.lower()


def raw_exact_equal(gold: object | None, pred: object | None) -> bool:
    return to_raw_string(gold) == to_raw_string(pred)
