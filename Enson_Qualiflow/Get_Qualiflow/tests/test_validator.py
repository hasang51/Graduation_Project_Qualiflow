from __future__ import annotations

import unittest

from app.schemas.extraction import (
    ExtractedItem,
    MechanicalProperties,
    UniversalDocumentExtraction,
)
from app.domain.validation_config import (
    DEFAULT_ELONGATION_RANGE,
    DEFAULT_TENSILE_RANGE,
    DEFAULT_YIELD_RANGE,
)
from app.services.validator import MATERIAL_SPECS, validate_document


def _make_extraction(items: list[ExtractedItem]) -> UniversalDocumentExtraction:
    return UniversalDocumentExtraction(
        supplier_name="ACME Steel",
        document_type="Mill Test Certificate",
        certificate_date="2024-01-31",
        total_items_detected=len(items),
        items=items,
        confidence_score=0.9,
        raw_model_confidence=0.9,
    )


def _compliant_s235_item() -> ExtractedItem:
    spec = MATERIAL_SPECS["S235JR"]
    return ExtractedItem(
        item_id="IPE-100",
        heat_number="812003694",
        grade="S235JR",
        weight_or_length="12000 KG",
        mechanical_properties=MechanicalProperties(
            yield_strength_mpa=spec["min_yield"] + 20,
            tensile_strength_mpa=spec["min_tensile"] + 30,
            elongation_percentage=spec["min_elongation"] + 4,
        ),
        row_confidence=1.0,
    )


class QualityThresholdBandsTests(unittest.TestCase):
    def test_yield_band_matches_documented_range(self):
        self.assertEqual((DEFAULT_YIELD_RANGE.lower, DEFAULT_YIELD_RANGE.upper), (80.0, 1500.0))

    def test_tensile_band_matches_documented_range(self):
        self.assertEqual((DEFAULT_TENSILE_RANGE.lower, DEFAULT_TENSILE_RANGE.upper), (120.0, 1800.0))

    def test_elongation_band_matches_documented_range(self):
        self.assertEqual((DEFAULT_ELONGATION_RANGE.lower, DEFAULT_ELONGATION_RANGE.upper), (1.0, 80.0))

    def test_values_within_band_are_not_suspicious(self):
        self.assertFalse(DEFAULT_YIELD_RANGE.is_suspicious(350.0))
        self.assertFalse(DEFAULT_TENSILE_RANGE.is_suspicious(500.0))
        self.assertFalse(DEFAULT_ELONGATION_RANGE.is_suspicious(25.0))

    def test_values_outside_band_are_suspicious(self):
        self.assertTrue(DEFAULT_YIELD_RANGE.is_suspicious(50.0))
        self.assertTrue(DEFAULT_YIELD_RANGE.is_suspicious(1600.0))
        self.assertTrue(DEFAULT_TENSILE_RANGE.is_suspicious(90.0))
        self.assertTrue(DEFAULT_ELONGATION_RANGE.is_suspicious(200.0))


class ValidateDocumentCompliantRowTests(unittest.TestCase):
    def test_compliant_s235_row_has_no_deviations(self):
        extraction = _make_extraction([_compliant_s235_item()])
        validated = validate_document(extraction)

        item = validated.items[0]
        self.assertIsNotNone(item.validation)
        self.assertTrue(item.validation.is_compliant)
        self.assertEqual(item.validation.deviations, [])
        self.assertFalse(item.needs_review)
        self.assertTrue(validated.is_compliant)


class ValidateDocumentNonCompliantRowTests(unittest.TestCase):
    def test_unknown_grade_is_flagged_for_review_not_as_non_compliant(self):
        """Phase 1 semantics: an unknown grade is unresolved, not non-compliant."""

        item = _compliant_s235_item()
        item.grade = "MYSTERY-GRADE"
        extraction = _make_extraction([item])

        validated = validate_document(extraction)
        flagged = validated.items[0]
        self.assertIsNotNone(flagged.validation)
        self.assertIsNone(
            flagged.validation.is_compliant,
            "unknown grade must not flip is_compliant to False",
        )
        self.assertEqual(flagged.validation.outcome, "NEEDS_REVIEW")
        self.assertTrue(flagged.needs_review)
        self.assertTrue(
            any("Unknown grade" in d for d in flagged.validation.deviations),
            flagged.validation.deviations,
        )
        # Document-level compliance is None because no row resolved.
        self.assertIsNone(validated.is_compliant)

    def test_unresolved_stainless_grade_is_unsupported_family(self):
        item = _compliant_s235_item()
        item.grade = "1.4301"
        extraction = _make_extraction([item])

        validated = validate_document(extraction)
        flagged = validated.items[0]
        self.assertIsNone(flagged.validation.is_compliant)
        self.assertEqual(flagged.validation.outcome, "UNSUPPORTED_SPEC_FAMILY")
        self.assertTrue(flagged.needs_review)

    def test_unsupported_family_is_review_safe(self):
        item = _compliant_s235_item()
        item.grade = "304"
        extraction = _make_extraction([item])
        validated = validate_document(extraction)
        flagged = validated.items[0]
        self.assertIsNone(flagged.validation.is_compliant)
        self.assertEqual(flagged.validation.outcome, "UNSUPPORTED_SPEC_FAMILY")
        self.assertTrue(flagged.needs_review)

    def test_observed_321_composite_grade_resolves_for_validation(self):
        item = ExtractedItem(
            item_id="1",
            heat_number="CH-22200",
            grade="1.4541/321 1.4878/321H UNS S32100",
            weight_or_length="2195 Kgs",
            mechanical_properties=MechanicalProperties(
                yield_strength_mpa=335.0,
                tensile_strength_mpa=638.0,
                elongation_percentage=52.0,
            ),
            row_confidence=0.9,
        )
        validated = validate_document(_make_extraction([item]))
        flagged = validated.items[0]
        self.assertTrue(flagged.validation.is_compliant)
        self.assertEqual(flagged.validation.outcome, "COMPLIANT")
        self.assertFalse(flagged.needs_review)

    def test_observed_sg2_supplier_grade_resolves_for_validation(self):
        item = ExtractedItem(
            item_id="1",
            heat_number="410537",
            grade="NOVOFIL SG2/NOVOBRONZE SG2",
            weight_or_length="1.080 Kg",
            mechanical_properties=MechanicalProperties(
                yield_strength_mpa=470.0,
                tensile_strength_mpa=560.0,
                elongation_percentage=26.0,
            ),
            row_confidence=0.9,
        )
        validated = validate_document(_make_extraction([item]))
        flagged = validated.items[0]
        self.assertTrue(flagged.validation.is_compliant)
        self.assertEqual(flagged.validation.outcome, "COMPLIANT")
        self.assertFalse(flagged.needs_review)

    def test_ambiguous_composite_grade_is_ambiguous(self):
        item = _compliant_s235_item()
        # Mixed-family composite should be ambiguous.
        item.grade = "S355J2 / 304L"
        extraction = _make_extraction([item])

        validated = validate_document(extraction)
        flagged = validated.items[0]
        self.assertIsNone(flagged.validation.is_compliant)
        self.assertEqual(flagged.validation.outcome, "NEEDS_REVIEW")
        self.assertTrue(flagged.needs_review)

    def test_yield_below_minimum_produces_deviation(self):
        item = _compliant_s235_item()
        item.mechanical_properties.yield_strength_mpa = 100.0
        extraction = _make_extraction([item])

        validated = validate_document(extraction)
        flagged = validated.items[0]
        self.assertFalse(flagged.validation.is_compliant)
        self.assertTrue(any("below minimum" in d for d in flagged.validation.deviations))

    def test_suspicious_yield_triggers_review_flag(self):
        item = _compliant_s235_item()
        item.mechanical_properties.yield_strength_mpa = 50.0
        extraction = _make_extraction([item])

        validated = validate_document(extraction)
        flagged = validated.items[0]
        self.assertTrue(flagged.needs_review)
        self.assertTrue(any("looks suspicious" in d for d in flagged.validation.deviations))


class ValidateDocumentRowCountTests(unittest.TestCase):
    def test_row_count_mismatch_triggers_review(self):
        extraction = _make_extraction([_compliant_s235_item()])
        extraction.total_items_detected = 5
        validated = validate_document(extraction)
        self.assertTrue(validated.needs_review)
        self.assertEqual(validated.total_items_detected, len(validated.items))
        self.assertIn("row_count_inconsistent", validated.review_reasons)


class ValidateDocumentHeatPatternTests(unittest.TestCase):
    def test_heat_number_pattern_outlier_is_flagged(self):
        base = _compliant_s235_item()
        base.heat_number = "812003694"

        second = _compliant_s235_item()
        second.heat_number = "812003710"

        outlier = _compliant_s235_item()
        outlier.heat_number = "HN-42"

        extraction = _make_extraction([base, second, outlier])
        validated = validate_document(extraction)

        self.assertTrue(validated.items[2].needs_review)
        self.assertTrue(
            any(
                "inconsistent with the dominant pattern" in d
                for d in (validated.items[2].validation.deviations or [])
            )
        )


class ValidateDocumentMissingMechanicalsTests(unittest.TestCase):
    def test_missing_mechanical_properties_is_tolerated(self):
        item = _compliant_s235_item()
        item.mechanical_properties = None
        extraction = _make_extraction([item])

        validated = validate_document(extraction)
        flagged = validated.items[0]
        self.assertIsNone(flagged.validation.is_compliant)
        self.assertEqual(flagged.validation.outcome, "NOT_VALIDATED")
        # is_compliant at document level is None when no item carries mechanical props
        self.assertIsNone(validated.is_compliant)


if __name__ == "__main__":
    unittest.main()
