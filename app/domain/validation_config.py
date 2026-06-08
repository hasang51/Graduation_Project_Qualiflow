from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class ProductCategoryConfig:
    tensile_strength_range: SuspiciousBand
    yield_strength_range: SuspiciousBand
    elongation_range: SuspiciousBand
    mandatory_fields: list[str]
    optional_fields: list[str]


# Default ranges for structural steel
DEFAULT_YIELD_RANGE = SuspiciousBand(80.0, 1500.0)
DEFAULT_TENSILE_RANGE = SuspiciousBand(120.0, 1800.0)
DEFAULT_ELONGATION_RANGE = SuspiciousBand(1.0, 80.0)
DEFAULT_MANDATORY_FIELDS = ["heat_number", "grade", "yield_strength_mpa", "tensile_strength_mpa", "elongation_percentage"]

VALIDATION_REGISTRY: dict[str, ProductCategoryConfig] = {
    "STRUCTURAL_STEEL": ProductCategoryConfig(
        tensile_strength_range=DEFAULT_TENSILE_RANGE,
        yield_strength_range=DEFAULT_YIELD_RANGE,
        elongation_range=DEFAULT_ELONGATION_RANGE,
        mandatory_fields=DEFAULT_MANDATORY_FIELDS.copy(),
        optional_fields=[],
    ),
    "PIPE": ProductCategoryConfig(
        tensile_strength_range=DEFAULT_TENSILE_RANGE,
        yield_strength_range=DEFAULT_YIELD_RANGE,
        elongation_range=DEFAULT_ELONGATION_RANGE,
        mandatory_fields=DEFAULT_MANDATORY_FIELDS.copy(),
        optional_fields=[],
    ),
    "WIRE_ROPE": ProductCategoryConfig(
        tensile_strength_range=SuspiciousBand(1200.0, 2500.0),
        # Wire rope doesn't typically have yield strength or elongation in the same way,
        # but we provide permissive bounds just in case they are extracted.
        yield_strength_range=SuspiciousBand(0.0, 2500.0),
        elongation_range=SuspiciousBand(0.0, 100.0),
        mandatory_fields=["heat_number", "grade", "tensile_strength_mpa"],
        optional_fields=["yield_strength_mpa", "elongation_percentage"],
    ),
}


def get_validation_config(category: str | None) -> ProductCategoryConfig:
    if category and category in VALIDATION_REGISTRY:
        return VALIDATION_REGISTRY[category]
    return VALIDATION_REGISTRY["STRUCTURAL_STEEL"]
