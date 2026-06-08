from __future__ import annotations

import unittest
from app.domain.grade_registry import known_canonical_grades, resolve_grade
from app.domain.spec_registry import get_spec, known_spec_grades, resolve_spec
from app.schemas.extraction import ExtractedItem, MechanicalProperties, UniversalDocumentExtraction
from app.services.validator import validate_document

class S195SpecTest(unittest.TestCase):
    def test_s195_resolves_to_material_spec(self):
        """Verify that S195 canonical grade resolves to the correct MaterialSpec."""
        grade_res = resolve_grade("S195")
        self.assertEqual(grade_res.canonical, "S195")
        
        spec_res = resolve_spec(grade_res)
        self.assertEqual(spec_res.status, "resolved")
        self.assertIsNotNone(spec_res.spec)
        self.assertEqual(spec_res.spec.canonical, "S195")
        self.assertEqual(spec_res.spec.min_yield_mpa, 195.0)
        self.assertEqual(spec_res.spec.min_tensile_mpa, 350.0)
        self.assertEqual(spec_res.spec.max_tensile_mpa, 620.0)
        self.assertEqual(spec_res.spec.min_elongation_pct, 20.0)
        self.assertEqual(get_spec("S195"), spec_res.spec)
        self.assertIn("S195", known_canonical_grades())
        self.assertIn("S195", known_spec_grades())

    def test_s195_aliases_resolve_to_material_spec(self):
        for raw in ("S195", "S195T", "EN 10255"):
            with self.subTest(raw=raw):
                grade_res = resolve_grade(raw)
                self.assertEqual(grade_res.status, "resolved")
                self.assertEqual(grade_res.canonical, "S195")

                spec_res = resolve_spec(grade_res)
                self.assertEqual(spec_res.status, "resolved")
                self.assertEqual(spec_res.spec, get_spec("S195"))

    def test_s195_validation_compliant(self):
        """Verify that a compliant S195 row is marked as COMPLIANT."""
        item = ExtractedItem(
            item_id="1",
            heat_number="12345",
            grade="S195",
            mechanical_properties=MechanicalProperties(
                yield_strength_mpa=200.0,   # > 195
                tensile_strength_mpa=400.0, # 350-620
                elongation_percentage=25.0  # > 20
            ),
            row_confidence=1.0
        )
        
        extraction = UniversalDocumentExtraction(
            supplier_name="Test Supplier",
            document_type="MTC",
            total_items_detected=1,
            items=[item],
            confidence_score=1.0,
            raw_model_confidence=1.0
        )
        
        validated = validate_document(extraction)
        val_item = validated.items[0]
        
        self.assertEqual(val_item.validation.outcome, "COMPLIANT")
        self.assertTrue(val_item.validation.is_compliant)
        self.assertEqual(len(val_item.validation.deviations), 0)
        self.assertNotIn("unresolved_spec", validated.review_reasons)
        self.assertFalse(any(reason.startswith("unresolved_spec") for reason in validated.review_reasons))

    def test_doc008_like_s195_row_does_not_emit_unresolved_spec(self):
        item = ExtractedItem(
            item_id=None,
            heat_number=None,
            grade="S195",
            mechanical_properties=MechanicalProperties(
                yield_strength_mpa=258.0,
                tensile_strength_mpa=421.0,
                elongation_percentage=29.0,
            ),
            needs_review=True,
            row_confidence=0.95,
        )

        extraction = UniversalDocumentExtraction(
            supplier_name="NOKSEL BORU SANAYI A.S.",
            document_type="Mill Test Certificate",
            total_items_detected=1,
            items=[item],
            needs_review=True,
            review_reasons=["critical_identifier_unverified"],
            confidence_score=0.95,
            raw_model_confidence=0.95,
        )

        validated = validate_document(extraction)

        self.assertEqual(validated.items[0].validation.outcome, "COMPLIANT")
        self.assertIn("critical_identifier_unverified", validated.review_reasons)
        self.assertNotIn("unresolved_spec", validated.review_reasons)
        self.assertFalse(any(reason.startswith("unresolved_spec") for reason in validated.review_reasons))

    def test_s195_validation_non_compliant_yield(self):
        """Verify that an S195 row with low yield is marked as NON_COMPLIANT."""
        item = ExtractedItem(
            item_id="1",
            heat_number="12345",
            grade="S195",
            mechanical_properties=MechanicalProperties(
                yield_strength_mpa=180.0,   # < 195
                tensile_strength_mpa=400.0, 
                elongation_percentage=25.0  
            ),
            row_confidence=1.0
        )
        
        extraction = UniversalDocumentExtraction(
            supplier_name="Test Supplier",
            document_type="MTC",
            total_items_detected=1,
            items=[item],
            confidence_score=1.0,
            raw_model_confidence=1.0
        )
        
        validated = validate_document(extraction)
        val_item = validated.items[0]
        
        self.assertEqual(val_item.validation.outcome, "NON_COMPLIANT")
        self.assertFalse(val_item.validation.is_compliant)
        self.assertTrue(any("Yield" in d and "below minimum" in d for d in val_item.validation.deviations))

if __name__ == "__main__":
    unittest.main()
