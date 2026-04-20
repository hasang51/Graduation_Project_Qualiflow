"""Shared numeric quality thresholds for QualiFlow.

These bands are used by both server-side row validation
(`app.services.validator`) and any evaluation/reporting helper
(`app.services.confidence`, `scripts/evaluate_extraction.py`) so that all
consumers agree on what counts as a "suspicious" mechanical-property value.

Keep these as single-source-of-truth constants. Do not duplicate the raw
numbers in other modules.
"""

from __future__ import annotations

from typing import Final


class SuspiciousBand:
    """Inclusive-exclusive band outside of which a value is flagged as suspicious.

    A value ``v`` is suspicious when ``v < lower`` or ``v > upper``.
    """

    __slots__ = ("lower", "upper")

    def __init__(self, lower: float, upper: float) -> None:
        self.lower = float(lower)
        self.upper = float(upper)

    def is_suspicious(self, value: float) -> bool:
        return value < self.lower or value > self.upper


YIELD_STRENGTH_MPA: Final[SuspiciousBand] = SuspiciousBand(80.0, 1500.0)
TENSILE_STRENGTH_MPA: Final[SuspiciousBand] = SuspiciousBand(120.0, 1800.0)
ELONGATION_PERCENTAGE: Final[SuspiciousBand] = SuspiciousBand(1.0, 80.0)


def is_suspicious(value: float, band: SuspiciousBand) -> bool:
    return band.is_suspicious(value)


__all__ = [
    "SuspiciousBand",
    "YIELD_STRENGTH_MPA",
    "TENSILE_STRENGTH_MPA",
    "ELONGATION_PERCENTAGE",
    "is_suspicious",
]
