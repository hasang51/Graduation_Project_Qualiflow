"""Locale-safe field-aware numeric parsing.

Mill-test certificates mix decimal conventions (``26,5`` vs. ``26.5``) and
frequently use a dot as a thousands separator (``1.097`` meaning ``1097``).
The LLM may return either a raw string or a float that inherits the wrong
convention; validating the float directly then breaks compliance logic.

This module applies **field-aware** normalisation:

- Each supported field has a plausible numeric band (reusing
  :mod:`app.services.quality_thresholds`).
- The parser scores both the "decimal separator" and the "thousands separator"
  interpretation of the raw text against that band.
- When only one interpretation is plausible the parser returns it.
- When both or neither is plausible the parser returns its best guess but
  marks ``uncertain=True`` so the validator / review policy routes to human
  review rather than silently committing a wrong number.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from app.services.quality_thresholds import (
    ELONGATION_PERCENTAGE,
    SuspiciousBand,
    TENSILE_STRENGTH_MPA,
    YIELD_STRENGTH_MPA,
)

FieldKind = Literal[
    "yield_mpa",
    "tensile_mpa",
    "elongation_pct",
    "length_mm",
    "weight_kg",
]

LocaleHint = Literal["auto", "comma_decimal", "dot_decimal"]


@dataclass(frozen=True)
class ParsedNumber:
    """Normalised numeric with full traceability."""

    value: float | None
    raw: str | float | int | None
    uncertain: bool
    reason: str
    promoted_thousands: bool = False
    interpretation: str = ""  # "decimal" | "thousands" | "float_passthrough" | "empty"

    def to_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "raw": self.raw,
            "uncertain": self.uncertain,
            "reason": self.reason,
            "promoted_thousands": self.promoted_thousands,
            "interpretation": self.interpretation,
        }


# Plausible bands (inclusive) used for "is this interpretation reasonable?".
# These are a superset of the "suspicious" band so that *unusual but physical*
# readings still count as plausible; the suspicious band is the validator's
# concern, not the parser's.
_PLAUSIBLE_BANDS: dict[FieldKind, SuspiciousBand] = {
    "yield_mpa": YIELD_STRENGTH_MPA,
    "tensile_mpa": TENSILE_STRENGTH_MPA,
    "elongation_pct": ELONGATION_PERCENTAGE,
}

# Fields where the value is usually an integer or a single-decimal-digit
# figure. Any formatting with 3 digits after a single separator is a strong
# signal of supplier-side thousands grouping rather than a real decimal.
_INTEGER_PREFERRING_FIELDS: set[FieldKind] = {
    "yield_mpa",
    "tensile_mpa",
    "elongation_pct",
}


_UNIT_PATTERN = re.compile(r"\s*(MPA|N/MM2|PSI|KSI|%|PCT|KG|MT|TON|TONS|PCS|MM|CM|M|FT)\s*$", re.IGNORECASE)


def _plausible(value: float, kind: FieldKind) -> bool:
    band = _PLAUSIBLE_BANDS.get(kind)
    if band is None:
        return True  # length / weight are not band-constrained here
    return not band.is_suspicious(value)


def _strip_unit(raw: str) -> str:
    text = raw.strip().replace("\u00a0", " ")
    return _UNIT_PATTERN.sub("", text).strip()


def _only_digits_and_sep(raw: str) -> str:
    # Keep digits, dot, comma, minus. Drop everything else.
    return re.sub(r"[^0-9.,\-]", "", raw)


def _count_occurrences(text: str, char: str) -> int:
    return sum(1 for c in text if c == char)


def _parse_float(text: str) -> float | None:
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _classify_pattern(cleaned: str) -> str:
    """Return a tag for the raw digit/separator pattern.

    ``cleaned`` is the string after unit-stripping and keeping only digits,
    dots, commas, and minus.
    """

    dots = _count_occurrences(cleaned, ".")
    commas = _count_occurrences(cleaned, ",")
    if dots == 0 and commas == 0:
        return "digits_only"
    if dots == 1 and commas == 0:
        return "single_dot"
    if dots == 0 and commas == 1:
        return "single_comma"
    if dots > 0 and commas > 0:
        return "mixed"
    return "many_same"


def _candidates_from_string(cleaned: str, locale: LocaleHint) -> list[tuple[float, str]]:
    """Return ``[(value, interpretation), ...]`` candidates for ``cleaned``.

    Each candidate is an alternative way of reading the numeric string. The
    caller picks the best one using field-aware plausibility.
    """

    pattern = _classify_pattern(cleaned)
    candidates: list[tuple[float, str]] = []

    if pattern == "digits_only":
        value = _parse_float(cleaned)
        if value is not None:
            candidates.append((value, "digits_only"))
        return candidates

    if pattern == "single_dot":
        integer_part, _, fractional_part = cleaned.partition(".")
        if locale == "comma_decimal":
            # Dot is a thousands separator in comma-decimal locales.
            promoted = _parse_float(integer_part + fractional_part)
            if promoted is not None:
                candidates.append((promoted, "thousands"))
            return candidates
        # "auto" and "dot_decimal"
        decimal_value = _parse_float(cleaned)
        if decimal_value is not None:
            candidates.append((decimal_value, "decimal"))
        if locale == "auto" and len(fractional_part) == 3 and integer_part:
            promoted = _parse_float(integer_part + fractional_part)
            if promoted is not None:
                candidates.append((promoted, "thousands"))
        return candidates

    if pattern == "single_comma":
        integer_part, _, fractional_part = cleaned.partition(",")
        if locale == "dot_decimal":
            # Comma is a thousands separator in dot-decimal locales.
            promoted = _parse_float(integer_part + fractional_part)
            if promoted is not None:
                candidates.append((promoted, "thousands"))
            return candidates
        decimal_value = _parse_float(integer_part + "." + fractional_part)
        if decimal_value is not None:
            candidates.append((decimal_value, "decimal"))
        if locale == "auto" and len(fractional_part) == 3 and integer_part:
            promoted = _parse_float(integer_part + fractional_part)
            if promoted is not None:
                candidates.append((promoted, "thousands"))
        return candidates

    if pattern == "mixed":
        # e.g. "1.234,56" (comma-decimal) or "1,234.56" (dot-decimal).
        dot_last = cleaned.rfind(".")
        comma_last = cleaned.rfind(",")
        if dot_last > comma_last:
            # dot-decimal: commas are thousands
            normalized = cleaned.replace(",", "")
            value = _parse_float(normalized)
            if value is not None:
                candidates.append((value, "dot_decimal_with_thousands"))
        else:
            # comma-decimal: dots are thousands
            normalized = cleaned.replace(".", "").replace(",", ".")
            value = _parse_float(normalized)
            if value is not None:
                candidates.append((value, "comma_decimal_with_thousands"))
        return candidates

    if pattern == "many_same":
        # e.g. "1.234.567": almost certainly thousands-grouped.
        stripped = cleaned.replace(".", "").replace(",", "")
        value = _parse_float(stripped)
        if value is not None:
            candidates.append((value, "thousands_grouped"))
        return candidates

    return candidates


def _pick_best_candidate(
    candidates: list[tuple[float, str]],
    kind: FieldKind,
) -> tuple[float, str, bool, str]:
    """Choose the best candidate; return ``(value, interp, uncertain, reason)``."""

    if not candidates:
        return 0.0, "empty", True, "no candidate interpretations"

    plausible = [(v, i) for v, i in candidates if _plausible(v, kind)]
    if len(plausible) == 1 and len(candidates) == 1:
        value, interp = plausible[0]
        return value, interp, False, "single plausible interpretation"

    if len(plausible) == 1 and len(candidates) > 1:
        value, interp = plausible[0]
        return value, interp, False, "only one plausible interpretation"

    if len(plausible) > 1:
        # Pick the first (decimal) by convention but mark uncertain.
        value, interp = plausible[0]
        return value, interp, True, "multiple plausible interpretations"

    # No candidate is plausible -> keep the first but mark uncertain.
    value, interp = candidates[0]
    return value, interp, True, "no plausible interpretation"


def parse_numeric(
    raw: str | float | int | None,
    *,
    kind: FieldKind,
    locale: LocaleHint = "auto",
) -> ParsedNumber:
    """Parse a mixed string/number into a :class:`ParsedNumber`.

    The parser never raises; callers inspect ``uncertain`` + ``value``.
    """

    if raw is None:
        return ParsedNumber(
            value=None, raw=raw, uncertain=False,
            reason="value is null", interpretation="empty",
        )

    # Float/int passthrough - but apply the thousands-promotion heuristic.
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        value = float(raw)
        if math.isnan(value) or math.isinf(value):
            return ParsedNumber(
                value=None, raw=raw, uncertain=True,
                reason="non-finite numeric", interpretation="float_passthrough",
            )
        if _plausible(value, kind):
            return ParsedNumber(
                value=value, raw=raw, uncertain=False,
                reason="float within plausible band",
                interpretation="float_passthrough",
            )
        # Not plausible as-is; try a ×1000 promotion when the float looks
        # like a supplier-formatted "1.097" (3 fractional digits).
        promoted_candidate = value * 1000.0
        fractional_str = f"{value:.6f}".rstrip("0").split(".")[1] if "." in f"{value:.6f}" else ""
        looks_like_thousands = 1 <= len(fractional_str) <= 3 and promoted_candidate == round(promoted_candidate)
        if looks_like_thousands and _plausible(promoted_candidate, kind):
            return ParsedNumber(
                value=promoted_candidate, raw=raw,
                uncertain=False, promoted_thousands=True,
                reason="float below plausible band promoted x1000",
                interpretation="float_promoted_thousands",
            )
        return ParsedNumber(
            value=value, raw=raw, uncertain=True,
            reason="float outside plausible band",
            interpretation="float_passthrough",
        )

    text = str(raw).strip()
    if not text:
        return ParsedNumber(
            value=None, raw=raw, uncertain=False,
            reason="empty string", interpretation="empty",
        )

    stripped = _strip_unit(text)
    cleaned = _only_digits_and_sep(stripped)
    if not cleaned:
        return ParsedNumber(
            value=None, raw=raw, uncertain=True,
            reason="no digits in string", interpretation="empty",
        )

    candidates = _candidates_from_string(cleaned, locale)
    value, interp, uncertain, reason = _pick_best_candidate(candidates, kind)
    promoted = interp in {"thousands", "thousands_grouped"}

    # Extra-conservative flag for integer-preferring fields: a 3-digit
    # fractional pattern whose ONLY plausible interpretation is the decimal
    # one is still suspicious formatting - surface it to the reviewer.
    if (
        kind in _INTEGER_PREFERRING_FIELDS
        and interp == "decimal"
        and _three_digit_fractional(cleaned)
        and not uncertain
    ):
        uncertain = True
        reason = "three-digit fractional pattern in integer-preferring field"

    return ParsedNumber(
        value=value,
        raw=raw,
        uncertain=uncertain,
        reason=reason,
        promoted_thousands=promoted,
        interpretation=interp,
    )


def _three_digit_fractional(cleaned: str) -> bool:
    """Return True if ``cleaned`` has exactly 3 digits after a single separator."""

    match = re.fullmatch(r"-?\d+[.,](\d{3})", cleaned)
    return match is not None


def parse_mechanical_properties(
    payload: dict[str, object] | None,
    *,
    locale: LocaleHint = "auto",
) -> tuple[dict[str, float | None], dict[str, ParsedNumber]]:
    """Parse a ``mechanical_properties`` dict.

    Returns ``(values_dict, trace_dict)``. The values dict has keys matching
    :class:`~app.schemas.extraction.MechanicalProperties` and the trace dict
    maps the same keys to :class:`ParsedNumber` objects for explainability.
    """

    if payload is None:
        return (
            {
                "yield_strength_mpa": None,
                "tensile_strength_mpa": None,
                "elongation_percentage": None,
            },
            {},
        )

    field_map: dict[str, FieldKind] = {
        "yield_strength_mpa": "yield_mpa",
        "tensile_strength_mpa": "tensile_mpa",
        "elongation_percentage": "elongation_pct",
    }

    values: dict[str, float | None] = {}
    trace: dict[str, ParsedNumber] = {}
    for key, kind in field_map.items():
        raw = payload.get(key)
        parsed = parse_numeric(raw, kind=kind, locale=locale)
        trace[key] = parsed
        values[key] = parsed.value
    return values, trace


__all__ = [
    "ParsedNumber",
    "parse_numeric",
    "parse_mechanical_properties",
]
