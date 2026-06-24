"""Robust parsers for numeric, unit, date, and dimension values."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_DATE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"), "ymd"),
    (re.compile(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$"), "dmy"),
    (re.compile(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2})$"), "dmy_short"),
]

_DIMENSION_DELIMITERS_RE = re.compile(r"\s*(?:x|×|\*|/|by)\s*", re.IGNORECASE)
_UNIT_SUFFIX_RE = re.compile(
    r"\s*(kg|kgs|kgs\.|kilogram|kilograms|g|gram|grams|t|ton|tons|tonne|tonnes|mt|mm|cm|m)\s*\.?$",
    re.IGNORECASE,
)
_NUMERIC_TOKEN_RE = re.compile(r"[-+]?\d[\d,.\s]*")


@dataclass(frozen=True)
class ParsedNumeric:
    value: float
    raw: str


@dataclass(frozen=True)
class ParsedUnitValue:
    value: float
    unit: str
    canonical_kg: float | None
    raw: str


@dataclass(frozen=True)
class ParsedDate:
    iso: str
    year: int
    month: int
    day: int
    raw: str


@dataclass(frozen=True)
class ParsedDimension:
    parts: tuple[tuple[float, str], ...]
    unit: str
    raw: str


def _normalize_decimal_separators(token: str) -> str:
    """Parse locale-style numbers: 2,195 -> 2195; 2,5 -> 2.5 when unambiguous."""
    cleaned = token.strip().replace(" ", "")
    if not cleaned:
        raise ValueError("empty numeric token")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = parts[0] + "." + parts[1]
        else:
            cleaned = cleaned.replace(",", "")
    return cleaned


def parse_numeric(value: object | None) -> ParsedNumeric | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _NUMERIC_TOKEN_RE.search(text)
    if not match:
        return None
    try:
        parsed = float(_normalize_decimal_separators(match.group(0)))
    except ValueError:
        return None
    return ParsedNumeric(value=parsed, raw=text)


_UNIT_TO_KG = {
    "kg": 1.0,
    "kgs": 1.0,
    "kilogram": 1.0,
    "kilograms": 1.0,
    "g": 0.001,
    "gram": 0.001,
    "grams": 0.001,
    "t": 1000.0,
    "ton": 1000.0,
    "tons": 1000.0,
    "tonne": 1000.0,
    "tonnes": 1000.0,
    "mt": 1000.0,
}

_LENGTH_UNITS = {"mm", "cm", "m"}


def _canonical_unit(unit: str) -> str:
    lowered = unit.lower().rstrip(".")
    aliases = {
        "kgs": "kg",
        "kilogram": "kg",
        "kilograms": "kg",
        "gram": "g",
        "grams": "g",
        "ton": "t",
        "tons": "t",
        "tonne": "t",
        "tonnes": "t",
        "mt": "t",
    }
    return aliases.get(lowered, lowered)


def parse_unit_value(value: object | None) -> ParsedUnitValue | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    numeric = parse_numeric(text)
    if numeric is None:
        return None
    unit_match = _UNIT_SUFFIX_RE.search(text)
    unit = _canonical_unit(unit_match.group(1)) if unit_match else ""
    canonical_kg = None
    if unit in _UNIT_TO_KG:
        canonical_kg = numeric.value * _UNIT_TO_KG[unit]
    return ParsedUnitValue(value=numeric.value, unit=unit, canonical_kg=canonical_kg, raw=text)


def parse_date(value: object | None, *, allow_incomplete: bool = False) -> ParsedDate | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for pattern, mode in _DATE_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        if mode == "ymd":
            year, month, day = (int(match.group(i)) for i in range(1, 4))
        elif mode == "dmy_short":
            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            year += 2000 if year < 70 else 1900
        else:
            day, month, year = (int(match.group(i)) for i in range(1, 4))
        try:
            canonical = date(year, month, day)
        except ValueError:
            return None
        return ParsedDate(iso=canonical.isoformat(), year=year, month=month, day=day, raw=text)
    if allow_incomplete:
        return None
    return None


def _extract_dimension_parts(text: str) -> tuple[list[tuple[float, str]], str]:
    chunks = [chunk.strip() for chunk in _DIMENSION_DELIMITERS_RE.split(text) if chunk.strip()]
    if not chunks:
        raise ValueError("no dimension parts")
    parts: list[tuple[float, str]] = []
    trailing_unit = ""
    for chunk in chunks:
        unit_match = _UNIT_SUFFIX_RE.search(chunk)
        unit = _canonical_unit(unit_match.group(1)) if unit_match else ""
        if unit:
            trailing_unit = unit
        numeric = parse_numeric(chunk)
        if numeric is None:
            raise ValueError(f"non-numeric dimension chunk: {chunk}")
        parts.append((numeric.value, unit or trailing_unit))
    unit = trailing_unit or (parts[-1][1] if parts else "")
    if unit:
        parts = [(value, part_unit or unit) for value, part_unit in parts]
    return parts, unit


def parse_dimension(value: object | None) -> ParsedDimension | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parts, unit = _extract_dimension_parts(text)
    except ValueError:
        return None
    return ParsedDimension(parts=tuple(parts), unit=unit, raw=text)
