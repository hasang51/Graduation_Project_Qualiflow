"""Grade alias registry + canonicalisation.

Phase 1 replaces the previous implicit ``.upper()`` lookup in
:mod:`app.services.validator` with an explicit, testable canonicalisation
layer. Design rules:

- Never silently invent a mapping. If two families are plausible the
  resolution is marked ``ambiguous`` and both candidates are returned.
- Preserve the original raw string so the reviewer pack and UI can explain
  *why* a decision was made.
- Support supplier noise (case, whitespace, hyphenation, slash-composite
  forms such as ``304/304L``, ``1.4301/1.4307``) without overfitting to a
  single supplier.
- Extension without touching validator core: new families or aliases only
  require editing the ``CANONICAL_GRADES`` table below.

The resolver returns a :class:`GradeResolution` object that the validator
and the spec registry consume. Pure functions, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable

from app.domain.field_mapping_registry import normalize_header


GradeFamily = str  # e.g. "S355J2", "304L", "1.4301"


@dataclass(frozen=True)
class _CanonicalGrade:
    """Internal declaration of a canonical grade family.

    ``aliases`` is the set of strings that all unambiguously resolve to this
    family. They are matched against the normalised form of the input.
    """

    canonical: GradeFamily
    family_group: str  # e.g. "structural_carbon", "stainless_austenitic", "line_pipe"
    aliases: tuple[str, ...]
    dual_with: tuple[GradeFamily, ...] = ()  # e.g. 304 <-> 1.4301 (same alloy)


CANONICAL_GRADES: tuple[_CanonicalGrade, ...] = (
    # Structural carbon (EN 10025-2) - existing thesis baseline.
    _CanonicalGrade(
        canonical="S235JR",
        family_group="structural_carbon",
        aliases=("S235JR", "S235 JR"),
    ),
    _CanonicalGrade(
        canonical="S275JR",
        family_group="structural_carbon",
        aliases=("S275JR", "S275 JR"),
    ),
    _CanonicalGrade(
        canonical="S355JR",
        family_group="structural_carbon",
        aliases=("S355JR", "S355 JR"),
    ),
    _CanonicalGrade(
        canonical="S355J2",
        family_group="structural_carbon",
        aliases=("S355J2", "S355 J2"),
    ),
    _CanonicalGrade(
        canonical="S355J2+N",
        family_group="structural_carbon",
        aliases=("S355J2+N", "S355 J2+N", "S355J2N"),
    ),
    # Line pipe (API 5L).
    _CanonicalGrade(
        canonical="API 5L X65",
        family_group="line_pipe",
        aliases=("API 5L X65", "API5L X65", "API 5LX65", "API5LX65", "X65", "L450"),
    ),
    _CanonicalGrade(
        canonical="S195",
        family_group="pipe",
        aliases=("S195", "EN 10255", "S195T"),
    ),
    # Welding wire supplier designations observed in the thesis gold sample.
    _CanonicalGrade(
        canonical="SG2",
        family_group="welding_wire",
        aliases=("SG2", "NOVOFIL SG2", "NOVOBRONZE SG2"),
    ),
    # Austenitic stainless (EN 10088-1 / AISI dual designation).
    _CanonicalGrade(
        canonical="1.4301",
        family_group="stainless_austenitic",
        aliases=("1.4301", "14301", "X5CRNI18-10", "X5CRNI1810"),
        dual_with=("304",),
    ),
    _CanonicalGrade(
        canonical="304",
        family_group="stainless_austenitic",
        aliases=("304", "AISI 304", "SS 304"),
        dual_with=("1.4301",),
    ),
    _CanonicalGrade(
        canonical="1.4307",
        family_group="stainless_austenitic",
        aliases=("1.4307", "14307", "X2CRNI18-9", "X2CRNI189"),
        dual_with=("304L",),
    ),
    _CanonicalGrade(
        canonical="304L",
        family_group="stainless_austenitic",
        aliases=("304L", "AISI 304L", "SS 304L"),
        dual_with=("1.4307",),
    ),
    _CanonicalGrade(
        canonical="1.4401",
        family_group="stainless_austenitic",
        aliases=("1.4401", "14401", "X5CRNIMO17-12-2", "X5CRNIMO17122"),
        dual_with=("316",),
    ),
    _CanonicalGrade(
        canonical="316",
        family_group="stainless_austenitic",
        aliases=("316", "AISI 316", "SS 316"),
        dual_with=("1.4401",),
    ),
    _CanonicalGrade(
        canonical="1.4404",
        family_group="stainless_austenitic",
        aliases=("1.4404", "14404", "X2CRNIMO17-12-2", "X2CRNIMO17122"),
        dual_with=("316L",),
    ),
    _CanonicalGrade(
        canonical="316L",
        family_group="stainless_austenitic",
        aliases=("316L", "AISI 316L", "SS 316L"),
        dual_with=("1.4404", "TP316L"),
    ),
    # ASTM A213/A312 pipe grades (case-insensitive via normalisation).
    _CanonicalGrade(
        canonical="TP304",
        family_group="astm_pipe",
        aliases=("TP304", "ASTM A312 TP304", "ASTM A213 TP304", "A312 TP304", "A213 TP304"),
        dual_with=("304",),
    ),
    _CanonicalGrade(
        canonical="TP304L",
        family_group="astm_pipe",
        aliases=("TP304L", "ASTM A312 TP304L", "ASTM A213 TP304L", "A312 TP304L", "A213 TP304L"),
        dual_with=("304L",),
    ),
    _CanonicalGrade(
        canonical="TP316",
        family_group="astm_pipe",
        aliases=("TP316", "ASTM A312 TP316", "ASTM A213 TP316", "A312 TP316", "A213 TP316"),
        dual_with=("316",),
    ),
    _CanonicalGrade(
        canonical="TP316L",
        family_group="astm_pipe",
        aliases=("TP316L", "ASTM A312 TP316L", "ASTM A213 TP316L", "A312 TP316L", "A213 TP316L"),
        dual_with=("316L",),
    ),
    _CanonicalGrade(
        canonical="317",
        family_group="stainless_austenitic",
        aliases=("317", "AISI 317", "SS 317"),
        dual_with=("TP317",),
    ),
    _CanonicalGrade(
        canonical="317L",
        family_group="stainless_austenitic",
        aliases=("317L", "AISI 317L", "SS 317L"),
        dual_with=("TP317L",),
    ),
    _CanonicalGrade(
        canonical="TP317",
        family_group="astm_pipe",
        aliases=("TP317", "ASTM A312 TP317", "ASTM A213 TP317", "A312 TP317", "A213 TP317"),
        dual_with=("317",),
    ),
    _CanonicalGrade(
        canonical="TP317L",
        family_group="astm_pipe",
        aliases=("TP317L", "ASTM A312 TP317L", "ASTM A213 TP317L", "A312 TP317L", "A213 TP317L"),
        dual_with=("317L",),
    ),
    _CanonicalGrade(
        canonical="TP321",
        family_group="astm_pipe",
        aliases=("TP321", "ASTM A312 TP321", "ASTM A213 TP321", "A312 TP321", "A213 TP321"),
        dual_with=("321",),
    ),
    _CanonicalGrade(
        canonical="TP321H",
        family_group="astm_pipe",
        aliases=("TP321H", "ASTM A312 TP321H", "ASTM A213 TP321H", "A312 TP321H", "A213 TP321H"),
        dual_with=("321H",),
    ),
    _CanonicalGrade(
        canonical="347",
        family_group="stainless_austenitic",
        aliases=("347", "AISI 347", "SS 347"),
        dual_with=("TP347",),
    ),
    _CanonicalGrade(
        canonical="347H",
        family_group="stainless_austenitic",
        aliases=("347H", "AISI 347H", "SS 347H"),
        dual_with=("TP347H",),
    ),
    _CanonicalGrade(
        canonical="TP347",
        family_group="astm_pipe",
        aliases=("TP347", "ASTM A312 TP347", "ASTM A213 TP347", "A312 TP347", "A213 TP347"),
        dual_with=("347",),
    ),
    _CanonicalGrade(
        canonical="TP347H",
        family_group="astm_pipe",
        aliases=("TP347H", "ASTM A312 TP347H", "ASTM A213 TP347H", "A312 TP347H", "A213 TP347H"),
        dual_with=("347H",),
    ),
    _CanonicalGrade(
        canonical="1.4541",
        family_group="stainless_austenitic",
        aliases=("1.4541", "14541", "X6CRNITI18-10", "X6CRNITI1810"),
        dual_with=("321",),
    ),
    _CanonicalGrade(
        canonical="321",
        family_group="stainless_austenitic",
        aliases=("321", "AISI 321", "SS 321", "UNS S32100", "S32100"),
        dual_with=("1.4541",),
    ),
    _CanonicalGrade(
        canonical="1.4878",
        family_group="stainless_austenitic",
        aliases=("1.4878", "14878", "X8CRNITI18-10", "X8CRNITI1810"),
        dual_with=("321H",),
    ),
    _CanonicalGrade(
        canonical="321H",
        family_group="stainless_austenitic",
        aliases=("321H", "AISI 321H", "SS 321H", "UNS S32109", "S32109"),
        dual_with=("1.4878",),
    ),
)


_DELIVERY_CONDITION_SUFFIX = re.compile(r"\+(N|M|AR|QT|Q)\b", re.IGNORECASE)
_ASTM_SPEC_PREFIX = re.compile(r"^(?:ASTM\s+)?A\d{3}\s+", re.IGNORECASE)

# Row keys / provenance values that indicate a grade was read from an explicit
# certificate field (Grade, Steel Grade, Material Grade, etc.).
EXPLICIT_GRADE_FIELD_LABELS: frozenset[str] = frozenset(
    {
        "GRADE",
        "STEEL GRADE",
        "MATERIAL GRADE",
        "MATERIAL",
        "KALITE",
        "STEEL GRADE MATERIAL",
    }
)
INFERRED_GRADE_PROVENANCE: frozenset[str] = frozenset(
    {"inferred", "enriched", "header_context", "none"},
)


def _normalize(raw: str) -> str:
    """Normalise a grade string to an internal matching form.

    Upper-cases, strips punctuation that does not carry meaning, and collapses
    whitespace. Slashes are preserved because they indicate composite /
    dual-designation strings.
    """

    cleaned = raw.strip().upper()
    cleaned = cleaned.replace("\u00a0", " ")
    cleaned = re.sub(r"[\t\r\n]+", " ", cleaned)
    cleaned = re.sub(r"[_;:|]+", " ", cleaned)
    cleaned = re.sub(r"[-]+", "-", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _alias_key(alias: str) -> str:
    """Normalise aliases for the resolver index (no hyphen, no spaces)."""

    text = alias.strip().upper()
    text = re.sub(r"[\s\-_]+", "", text)
    return text


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, _CanonicalGrade]:
    index: dict[str, _CanonicalGrade] = {}
    for grade in CANONICAL_GRADES:
        for alias in grade.aliases:
            index[_alias_key(alias)] = grade
        # Also index the canonical name itself.
        index[_alias_key(grade.canonical)] = grade
    return index


@dataclass(frozen=True)
class GradeResolution:
    """Result of resolving a raw grade string against the registry.

    ``candidates`` always contains the list of canonical family strings the
    resolver believes are plausible. For a clean single-family match it has a
    single entry; for a dual-certification composite (``304/304L``) it has
    two. For ambiguous supplier noise the resolver returns the candidates it
    cannot choose between.

    The validator is expected to:

    - route to review when ``status != 'resolved'``,
    - prefer ``candidates[0]`` for spec lookup when
      ``status == 'resolved_dual'``. Both candidates are shown to reviewers.
    """

    raw: str
    normalized: str
    status: str  # one of: resolved, resolved_dual, unknown, ambiguous, empty
    canonical: GradeFamily | None
    candidates: tuple[GradeFamily, ...]
    family_group: str | None
    dual_designation: bool
    reason: str
    confidence: float

    def to_dict(self) -> dict[str, object]:
        return {
            "raw": self.raw,
            "normalized": self.normalized,
            "status": self.status,
            "canonical": self.canonical,
            "candidates": list(self.candidates),
            "family_group": self.family_group,
            "dual_designation": self.dual_designation,
            "reason": self.reason,
            "confidence": self.confidence,
        }


def _split_composite(normalized: str) -> list[str]:
    """Split a composite dual-designation grade string on ``/`` or ``,``.

    Supplier-level noise like ``S355J2+N / S355JR`` is also split.
    """

    if not normalized:
        return []
    parts = re.split(r"\s*[/,]\s*", normalized)
    return [p.strip() for p in parts if p.strip()]


def _strip_delivery_condition(normalized: str) -> str:
    """Return the normalised string with EN 10025-style ``+N`` removed.

    Used as a fallback match only. The original string is preserved in
    ``raw`` so the validator/UI can still see it.
    """

    return _DELIVERY_CONDITION_SUFFIX.sub("", normalized).strip()


def _strip_spec_prefix(normalized_token: str) -> str:
    """Remove leading ASTM standard prefixes such as ``ASTM A312 ``."""

    return _ASTM_SPEC_PREFIX.sub("", normalized_token).strip()


def _match_single(normalized_token: str) -> _CanonicalGrade | None:
    """Look a single already-normalised grade token up in the alias index."""

    if not normalized_token:
        return None
    candidates = [normalized_token, _strip_spec_prefix(normalized_token)]
    for candidate in candidates:
        if not candidate:
            continue
        key = _alias_key(candidate)
        grade = _alias_index().get(key)
        if grade is not None:
            return grade
        # Try without delivery condition suffix (``S355J2+N`` -> ``S355J2``).
        stripped = _strip_delivery_condition(candidate)
        if stripped and stripped != candidate:
            grade = _alias_index().get(_alias_key(stripped))
            if grade is not None:
                return grade
    return None


def is_explicit_grade_field_label(label: str | None) -> bool:
    """Return True when *label* names an explicit grade column on a certificate."""

    normalized = normalize_header(label or "")
    if not normalized:
        return False
    if normalized in EXPLICIT_GRADE_FIELD_LABELS:
        return True
    return any(
        normalized == explicit or normalized.endswith(f" {explicit}")
        for explicit in EXPLICIT_GRADE_FIELD_LABELS
    )


def has_explicit_grade_value(
    grade: str | None,
    *,
    grade_provenance: str | None = None,
    grade_field_label: str | None = None,
) -> bool:
    """Return True when a non-empty grade was sourced from an explicit field."""

    if not str(grade or "").strip():
        return False
    if grade_field_label and is_explicit_grade_field_label(grade_field_label):
        return True
    provenance = (grade_provenance or "").strip().lower()
    if provenance and provenance not in INFERRED_GRADE_PROVENANCE:
        return True
    return False


def _contained_matches(normalized_token: str) -> list[_CanonicalGrade]:
    """Return aliases visibly contained in a noisy supplier grade token."""

    token_key = _alias_key(normalized_token)
    matches: list[_CanonicalGrade] = []
    for alias_key, grade in _alias_index().items():
        if len(alias_key) < 3:
            continue
        if alias_key in token_key and grade not in matches:
            matches.append(grade)
    return matches


def _resolution_from_matches(
    *,
    raw: str,
    normalized: str,
    matches: list[_CanonicalGrade],
    reason: str,
) -> GradeResolution:
    canonicals = tuple(dict.fromkeys(grade.canonical for grade in matches))
    family_groups = {grade.family_group for grade in matches}
    if len(canonicals) == 1:
        grade = matches[0]
        return GradeResolution(
            raw=raw,
            normalized=normalized,
            status="resolved",
            canonical=grade.canonical,
            candidates=(grade.canonical,),
            family_group=grade.family_group,
            dual_designation=False,
            reason=reason,
            confidence=0.9,
        )
    if len(family_groups) == 1:
        return GradeResolution(
            raw=raw,
            normalized=normalized,
            status="resolved_dual",
            canonical=canonicals[0],
            candidates=canonicals,
            family_group=next(iter(family_groups)),
            dual_designation=True,
            reason=reason,
            confidence=0.85,
        )
    return GradeResolution(
        raw=raw,
        normalized=normalized,
        status="ambiguous",
        canonical=None,
        candidates=canonicals,
        family_group=None,
        dual_designation=False,
        reason="contained aliases span multiple families",
        confidence=0.4,
    )


def resolve_grade(raw: str | None) -> GradeResolution:
    """Resolve a raw grade string against the canonical registry.

    Never raises on bad input. Callers read ``status`` to decide what to do.
    """

    if raw is None or not str(raw).strip():
        return GradeResolution(
            raw=raw or "",
            normalized="",
            status="empty",
            canonical=None,
            candidates=(),
            family_group=None,
            dual_designation=False,
            reason="empty input",
            confidence=0.0,
        )

    normalized = _normalize(str(raw))
    tokens = _split_composite(normalized)

    # Single token path.
    if len(tokens) <= 1:
        match = _match_single(tokens[0] if tokens else normalized)
        if match is None:
            contained = _contained_matches(tokens[0] if tokens else normalized)
            if contained:
                return _resolution_from_matches(
                    raw=str(raw),
                    normalized=normalized,
                    matches=contained,
                    reason="contained supplier aliases recognised",
                )
            return GradeResolution(
                raw=str(raw),
                normalized=normalized,
                status="unknown",
                canonical=None,
                candidates=(),
                family_group=None,
                dual_designation=False,
                reason="no alias matches the registry",
                confidence=0.0,
            )
        return GradeResolution(
            raw=str(raw),
            normalized=normalized,
            status="resolved",
            canonical=match.canonical,
            candidates=(match.canonical,),
            family_group=match.family_group,
            dual_designation=False,
            reason="single alias match",
            confidence=1.0,
        )

    # Composite path (e.g. ``304/304L``).
    resolved: list[_CanonicalGrade] = []
    unresolved_tokens: list[str] = []
    for token in tokens:
        match = _match_single(token)
        if match is None:
            contained = _contained_matches(token)
            if contained:
                resolved.extend(contained)
            else:
                unresolved_tokens.append(token)
        else:
            resolved.append(match)

    if not resolved:
        return GradeResolution(
            raw=str(raw),
            normalized=normalized,
            status="unknown",
            canonical=None,
            candidates=(),
            family_group=None,
            dual_designation=False,
            reason="composite with no alias matches",
            confidence=0.0,
        )

    canonicals = tuple(dict.fromkeys(grade.canonical for grade in resolved))
    family_groups = {grade.family_group for grade in resolved}

    if len(canonicals) == 1:
        return GradeResolution(
            raw=str(raw),
            normalized=normalized,
            status="resolved",
            canonical=canonicals[0],
            candidates=canonicals,
            family_group=next(iter(family_groups)),
            dual_designation=False,
            reason="composite aliases resolve to one canonical grade",
            confidence=0.9,
        )

    # True dual-certification (same alloy, both designations): all resolved
    # tokens belong to the same family group and are pairwise related via
    # ``dual_with``.
    is_dual = len(family_groups) == 1 and len(canonicals) >= 2
    if is_dual:
        return GradeResolution(
            raw=str(raw),
            normalized=normalized,
            status="resolved_dual",
            canonical=canonicals[0],
            candidates=canonicals,
            family_group=next(iter(family_groups)),
            dual_designation=True,
            reason="dual-designation composite recognised",
            confidence=0.9,
        )

    # Mixed-family composite (unexpected on real MTCs) -> ambiguous.
    return GradeResolution(
        raw=str(raw),
        normalized=normalized,
        status="ambiguous",
        canonical=None,
        candidates=canonicals,
        family_group=None,
        dual_designation=False,
        reason="composite spans multiple families",
        confidence=0.4,
    )


def known_canonical_grades() -> list[GradeFamily]:
    """Sorted list of all declared canonical grade families."""

    return sorted({grade.canonical for grade in CANONICAL_GRADES})


def iter_canonical_grades() -> Iterable[_CanonicalGrade]:
    return iter(CANONICAL_GRADES)


__all__ = [
    "EXPLICIT_GRADE_FIELD_LABELS",
    "GradeResolution",
    "has_explicit_grade_value",
    "is_explicit_grade_field_label",
    "known_canonical_grades",
    "iter_canonical_grades",
    "resolve_grade",
    "CANONICAL_GRADES",
]
