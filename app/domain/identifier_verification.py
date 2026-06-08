"""OCR-aware verification helpers for critical traceability identifiers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

CRITICAL_TRACEABILITY_FIELDS: tuple[str, ...] = (
    "heat_number",
    "batch_number",
    "lot_number",
    "colata_number",
    "cast_number",
    "charge_number",
    "coil_number",
    "traceability_identifier_value",
)

OCR_UNCERTAIN_REASON = "traceability_identifier_ocr_uncertain"
IDENTIFIER_CONFLICT_REASON = "traceability_identifier_conflict"
IDENTIFIER_OCR_USER_MESSAGE = (
    "Traceability identifier contains visually ambiguous OCR characters and requires human verification."
)

_OCR_SUSPICIOUS_LETTERS = frozenset("OILSBZG")
_CONFUSABLE_GROUPS: tuple[frozenset[str], ...] = (
    frozenset("O0"),
    frozenset("IL1"),
    frozenset("S5"),
    frozenset("B8"),
    frozenset("Z2"),
    frozenset("G6"),
)
_NON_ALNUM_RE = re.compile(r"[^A-Z0-9]+")
_PREFIX_BODY_RE = re.compile(r"^([A-Z]{1,2})[-]?(\d.*)$")
_EXPLICIT_MIXED_SERIAL_RE = re.compile(r"^[A-Z]{2,}[A-Z0-9]*$")


@dataclass(frozen=True)
class IdentifierCandidate:
    field: str
    value: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "value": self.value, "source": self.source}


@dataclass
class IdentifierVerificationAssessment:
    field: str
    accepted_value: str | None
    ocr_uncertain: bool = False
    conflict: bool = False
    candidates: list[IdentifierCandidate] = field(default_factory=list)
    conflicting_pairs: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "accepted_value": self.accepted_value,
            "ocr_uncertain": self.ocr_uncertain,
            "conflict": self.conflict,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "conflicting_pairs": list(self.conflicting_pairs),
        }


def normalize_identifier_for_comparison(value: str) -> str:
    """Upper-case identifier with spaces/punctuation removed for comparison."""

    text = str(value).strip().upper()
    text = text.replace("\u00a0", "")
    text = _NON_ALNUM_RE.sub("", text)
    return text


def chars_visually_confusable(
    left: str,
    right: str,
    *,
    index: int,
    text: str,
) -> bool:
    """Return True when two characters are visually confusable at *index*."""

    if not left or not right:
        return False
    a, b = left.upper(), right.upper()
    if a == b:
        return True
    for group in _CONFUSABLE_GROUPS:
        if a in group and b in group:
            if a == "G" or b == "G":
                prev_ch = text[index - 1] if index > 0 else ""
                next_ch = text[index + 1] if index + 1 < len(text) else ""
                return prev_ch.isdigit() and next_ch.isdigit()
            return True
    return False


def differ_by_single_suspicious_substitution(left: str, right: str) -> bool:
    """True when normalized values differ at exactly one suspicious position."""

    if left == right:
        return False
    if len(left) != len(right):
        return False
    diff_index: int | None = None
    diff_chars: tuple[str, str] | None = None
    for index, (a, b) in enumerate(zip(left, right)):
        if a == b:
            continue
        if diff_index is not None:
            return False
        diff_index = index
        diff_chars = (a, b)
    if diff_index is None or diff_chars is None:
        return False
    a, b = diff_chars
    if chars_visually_confusable(a, b, index=diff_index, text=left):
        return True
    return a.isdigit() and b.isdigit()


def has_suspicious_ocr_characters(value: str) -> bool:
    """Detect OCR-risk letters inside mostly-numeric identifier codes."""

    normalized = normalize_identifier_for_comparison(value)
    if not normalized:
        return False

    alnum = [char for char in normalized if char.isalnum()]
    if len(alnum) < 3:
        return False

    letter_count = sum(char.isalpha() for char in alnum)
    digit_count = sum(char.isdigit() for char in alnum)
    if letter_count == 0:
        return False

    # Explicit mixed alphanumeric serials such as LS210612G8 are allowed.
    if (
        _EXPLICIT_MIXED_SERIAL_RE.fullmatch(normalized)
        and letter_count >= 2
        and letter_count / len(alnum) >= 0.2
    ):
        return False

    prefix_match = _PREFIX_BODY_RE.match(normalized)
    if prefix_match and len(prefix_match.group(1)) <= 2 and digit_count >= 3:
        prefix = prefix_match.group(1)
        body = prefix_match.group(2)
        body_letters = [char for char in body if char.isalpha()]
        if not body_letters:
            if len(prefix) == 1 and prefix in _OCR_SUSPICIOUS_LETTERS and body.isdigit():
                return True
            return False
        check_text = body
    else:
        if digit_count / len(alnum) < 0.7:
            return False
        check_text = normalized

    for index, char in enumerate(check_text):
        if not char.isalpha() or char not in _OCR_SUSPICIOUS_LETTERS:
            continue
        prev_ch = check_text[index - 1] if index > 0 else ""
        next_ch = check_text[index + 1] if index + 1 < len(check_text) else ""
        if char == "G":
            if prev_ch.isdigit() and next_ch.isdigit():
                return True
            if index == 0 and digit_count / len(alnum) >= 0.7:
                return True
            continue
        return True
    return False


def _candidate_values(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return [str(raw)]
    if isinstance(raw, list):
        values: list[str] = []
        for entry in raw:
            values.extend(_candidate_values(entry))
        return values
    if isinstance(raw, dict):
        if "value" in raw:
            return _candidate_values(raw.get("value"))
        return []
    return []


def collect_field_candidates(
    *,
    field: str,
    accepted_value: Any,
    raw_identifier_candidates: dict[str, Any] | None,
    extra_candidates: Iterable[IdentifierCandidate] | None = None,
) -> list[IdentifierCandidate]:
    """Gather all known candidates for one identifier field."""

    seen: set[tuple[str, str]] = set()
    collected: list[IdentifierCandidate] = []

    def add(value: Any, source: str) -> None:
        for text in _candidate_values(value):
            key = (field, text)
            if key in seen:
                continue
            seen.add(key)
            collected.append(IdentifierCandidate(field=field, value=text, source=source))

    add(accepted_value, "accepted")
    raw_map = raw_identifier_candidates or {}
    raw_entry = raw_map.get(field)
    if raw_entry is not None:
        if isinstance(raw_entry, list):
            for index, entry in enumerate(raw_entry):
                if isinstance(entry, dict):
                    add(entry.get("value"), str(entry.get("source") or f"candidate:{index}"))
                else:
                    add(entry, f"candidate:{index}")
        else:
            add(raw_entry, "raw_identifier_candidates")
    if extra_candidates:
        for candidate in extra_candidates:
            if candidate.field != field:
                continue
            add(candidate.value, candidate.source)
    return collected


def assess_identifier_field(
    *,
    field: str,
    accepted_value: Any,
    raw_identifier_candidates: dict[str, Any] | None = None,
    extra_candidates: Iterable[IdentifierCandidate] | None = None,
) -> IdentifierVerificationAssessment:
    """Assess OCR uncertainty and single-character candidate conflicts."""

    candidates = collect_field_candidates(
        field=field,
        accepted_value=accepted_value,
        raw_identifier_candidates=raw_identifier_candidates,
        extra_candidates=extra_candidates,
    )
    accepted_text = str(accepted_value).strip() if accepted_value is not None else ""
    assessment = IdentifierVerificationAssessment(
        field=field,
        accepted_value=accepted_text or None,
        candidates=candidates,
    )
    if accepted_text and has_suspicious_ocr_characters(accepted_text):
        assessment.ocr_uncertain = True

    normalized_values = {
        normalize_identifier_for_comparison(candidate.value)
        for candidate in candidates
        if candidate.value
    }
    normalized_list = sorted(normalized_values)
    for index, left in enumerate(normalized_list):
        for right in normalized_list[index + 1 :]:
            if differ_by_single_suspicious_substitution(left, right):
                assessment.conflict = True
                assessment.conflicting_pairs.append((left, right))
    return assessment


__all__ = [
    "CRITICAL_TRACEABILITY_FIELDS",
    "IDENTIFIER_CONFLICT_REASON",
    "IDENTIFIER_OCR_USER_MESSAGE",
    "OCR_UNCERTAIN_REASON",
    "IdentifierCandidate",
    "IdentifierVerificationAssessment",
    "assess_identifier_field",
    "chars_visually_confusable",
    "collect_field_candidates",
    "differ_by_single_suspicious_substitution",
    "has_suspicious_ocr_characters",
    "normalize_identifier_for_comparison",
]
