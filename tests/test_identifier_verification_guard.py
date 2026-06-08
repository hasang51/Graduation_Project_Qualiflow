from __future__ import annotations

import unittest

from app.domain.identifier_verification import (
    IDENTIFIER_CONFLICT_REASON,
    IDENTIFIER_OCR_USER_MESSAGE,
    OCR_UNCERTAIN_REASON,
    assess_identifier_field,
    differ_by_single_suspicious_substitution,
    has_suspicious_ocr_characters,
    normalize_identifier_for_comparison,
)
from app.schemas.extraction import ExtractedItem, MechanicalProperties, UniversalDocumentExtraction, ValidationResult
from app.services.identifier_verification_guard import apply_identifier_verification_guard


class IdentifierVerificationDomainTests(unittest.TestCase):
    def test_normalizes_punctuation_for_comparison(self):
        self.assertEqual(normalize_identifier_for_comparison("CH-22200"), "CH22200")
        self.assertTrue(
            differ_by_single_suspicious_substitution(
                normalize_identifier_for_comparison("CH-22200"),
                normalize_identifier_for_comparison("CH-22300"),
            )
        )

    def test_g202_in_mostly_numeric_field_is_ocr_uncertain(self):
        self.assertTrue(has_suspicious_ocr_characters("G202"))

    def test_ls210612g8_explicit_alphanumeric_allowed(self):
        self.assertFalse(has_suspicious_ocr_characters("LS210612G8"))

    def test_ch_prefix_numeric_body_allowed(self):
        self.assertFalse(has_suspicious_ocr_characters("CH-22200"))


class IdentifierVerificationGuardTests(unittest.TestCase):
    def _extraction_with_item(self, **item_overrides) -> UniversalDocumentExtraction:
        item_values = {
            "item_id": "1",
            "heat_number": "CH-22200",
            "grade": "TP317L",
            "mechanical_properties": MechanicalProperties(
                yield_strength_mpa=335.0,
                tensile_strength_mpa=638.0,
                elongation_percentage=52.0,
            ),
            "validation": ValidationResult(is_compliant=True, deviations=[], outcome="COMPLIANT"),
            "row_confidence": 0.9,
            "identifier_visibility_verified": True,
            "traceability_status": "VERIFIED",
        }
        item_values.update(item_overrides)
        item = ExtractedItem(**item_values)
        return UniversalDocumentExtraction(
            supplier_name="Supplier",
            document_type="Mill Test Certificate",
            total_items_detected=1,
            items=[item],
            confidence_score=0.9,
            identifier_visibility_verified=True,
        )

    def test_conflicting_candidates_trigger_review_without_changing_value(self):
        assessment = assess_identifier_field(
            field="heat_number",
            accepted_value="CH-22200",
            raw_identifier_candidates={
                "heat_number": [{"value": "CH-22300", "source": "vision_alt"}],
            },
        )
        self.assertTrue(assessment.conflict)
        self.assertEqual(assessment.accepted_value, "CH-22200")

        extraction = self._extraction_with_item(
            raw_identifier_candidates={
                "heat_number": [{"value": "CH-22300", "source": "vision_alt"}],
            }
        )
        result = apply_identifier_verification_guard(extraction)
        item = extraction.items[0]

        self.assertEqual(item.heat_number, "CH-22200")
        self.assertTrue(item.needs_review)
        self.assertFalse(item.identifier_visibility_verified)
        self.assertIn(IDENTIFIER_CONFLICT_REASON, result.tokens)
        self.assertIn(IDENTIFIER_CONFLICT_REASON, extraction.review_reasons)
        self.assertTrue(item.raw_identifier_candidates.get("heat_number"))

    def test_g202_triggers_ocr_uncertain_review(self):
        extraction = self._extraction_with_item(heat_number="G202")
        result = apply_identifier_verification_guard(extraction)
        item = extraction.items[0]

        self.assertEqual(item.heat_number, "G202")
        self.assertTrue(item.needs_review)
        self.assertFalse(item.identifier_visibility_verified)
        self.assertIn(OCR_UNCERTAIN_REASON, result.tokens)
        self.assertIn(IDENTIFIER_OCR_USER_MESSAGE, extraction.ai_analysis_remarks or "")

    def test_ls210612g8_allowed_without_ocr_flag(self):
        extraction = self._extraction_with_item(heat_number="LS210612G8")
        result = apply_identifier_verification_guard(extraction)
        item = extraction.items[0]

        self.assertEqual(item.heat_number, "LS210612G8")
        self.assertNotIn(OCR_UNCERTAIN_REASON, result.tokens)
        self.assertNotIn(IDENTIFIER_CONFLICT_REASON, result.tokens)
        self.assertFalse(item.needs_review)


if __name__ == "__main__":
    unittest.main()
