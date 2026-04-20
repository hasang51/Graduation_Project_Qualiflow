from __future__ import annotations

import unittest

from app.schemas.extraction import (
    ExtractedItem,
    MechanicalProperties,
    UniversalDocumentExtraction,
    ValidationResult,
)
from app.services.document_profiler import DocumentProfile
from app.services.review_policy import apply_review_policy


def _degraded_profile() -> DocumentProfile:
    return DocumentProfile(
        document_id="doc1",
        filename="x.pdf",
        page_count=1,
        has_text_layer=False,
        text_density=0.0,
        blur_score=40.0,
        noise_score=30.0,
        table_presence_hint=True,
        quality_class="scan_degraded",
        reasons=["blur_high", "noise_high"],
    )


def _clean_profile() -> DocumentProfile:
    return DocumentProfile(
        document_id="doc2",
        filename="y.pdf",
        page_count=2,
        has_text_layer=True,
        text_density=0.4,
        blur_score=300.0,
        noise_score=5.0,
        table_presence_hint=False,
        quality_class="digital_clean",
        reasons=["text_layer_present"],
    )


def _make_extraction(
    *,
    items: list[ExtractedItem],
    total_items_detected: int | None = None,
    confidence_score: float = 0.9,
    needs_review: bool = False,
    review_reasons: list[str] | None = None,
    status: str | None = "COMPLETED",
) -> UniversalDocumentExtraction:
    return UniversalDocumentExtraction(
        supplier_name="Supplier",
        document_type="Mill Test Certificate",
        certificate_date=None,
        total_items_detected=total_items_detected if total_items_detected is not None else len(items),
        items=items,
        confidence_score=confidence_score,
        raw_model_confidence=confidence_score,
        ai_analysis_remarks=None,
        is_compliant=True,
        status=status,
        needs_review=needs_review,
        review_reasons=review_reasons or [],
    )


class ReviewPolicyTests(unittest.TestCase):
    def test_no_items_triggers_no_items_extracted_token(self):
        extraction = _make_extraction(items=[], total_items_detected=3)
        decision = apply_review_policy(extraction, profile=_clean_profile())
        self.assertIn("no_items_extracted", decision.structured_reasons)
        self.assertIn("row_count_inconsistent", decision.structured_reasons)
        self.assertTrue(decision.review_required)

    def test_missing_critical_numeric_all_rows_emits_token(self):
        items = [
            ExtractedItem(
                item_id="1",
                heat_number="H1",
                grade="S355J2",
                weight_or_length="100 kg",
                mechanical_properties=MechanicalProperties(
                    yield_strength_mpa=None,
                    tensile_strength_mpa=None,
                    elongation_percentage=25.0,
                ),
                row_confidence=0.9,
            ),
        ]
        extraction = _make_extraction(items=items)
        decision = apply_review_policy(extraction, profile=_clean_profile())
        self.assertIn("missing_critical_field:yield_strength", decision.structured_reasons)
        self.assertIn("missing_critical_field:tensile_strength", decision.structured_reasons)

    def test_degraded_document_emits_document_quality_token(self):
        items = [
            ExtractedItem(
                item_id="1",
                heat_number="H1",
                grade="S355J2",
                weight_or_length="100 kg",
                mechanical_properties=MechanicalProperties(
                    yield_strength_mpa=380.0,
                    tensile_strength_mpa=500.0,
                    elongation_percentage=25.0,
                ),
                row_confidence=0.5,
            ),
        ]
        extraction = _make_extraction(items=items, confidence_score=0.5, needs_review=True)
        decision = apply_review_policy(extraction, profile=_degraded_profile())
        self.assertIn("document_quality:scan_degraded", decision.structured_reasons)

    def test_validation_conflict_token_on_suspicious(self):
        mp = MechanicalProperties(
            yield_strength_mpa=99999.0,  # absurd
            tensile_strength_mpa=500.0,
            elongation_percentage=25.0,
        )
        deviation = "Yield 99999.0 MPa looks suspicious."
        item = ExtractedItem(
            item_id="1",
            heat_number="H1",
            grade="S355J2",
            weight_or_length="100 kg",
            mechanical_properties=mp,
            validation=ValidationResult(is_compliant=False, deviations=[deviation]),
            needs_review=True,
            row_confidence=0.4,
        )
        extraction = _make_extraction(
            items=[item],
            confidence_score=0.85,
            needs_review=True,
            review_reasons=["numeric fields are suspicious"],
        )
        decision = apply_review_policy(extraction, profile=_clean_profile())
        self.assertIn("validation_conflict:suspicious_numeric_values", decision.structured_reasons)
        self.assertIn("validation_conflict:row_non_compliant", decision.structured_reasons)

    def test_confidence_below_threshold_token(self):
        items = [
            ExtractedItem(
                item_id="1",
                heat_number="H1",
                grade="S355J2",
                weight_or_length="100 kg",
                mechanical_properties=MechanicalProperties(
                    yield_strength_mpa=400.0,
                    tensile_strength_mpa=520.0,
                    elongation_percentage=24.0,
                ),
                row_confidence=0.6,
            ),
        ]
        extraction = _make_extraction(items=items, confidence_score=0.4)
        decision = apply_review_policy(
            extraction,
            profile=_clean_profile(),
            review_confidence_threshold=0.75,
        )
        self.assertIn("confidence_below_threshold", decision.structured_reasons)
        self.assertTrue(decision.review_required)

    def test_unknown_grade_emits_unresolved_grade_token(self):
        item = ExtractedItem(
            item_id="1",
            heat_number="H1",
            grade="MYSTERY-GRADE",
            weight_or_length="100 kg",
            mechanical_properties=MechanicalProperties(
                yield_strength_mpa=380.0,
                tensile_strength_mpa=500.0,
                elongation_percentage=25.0,
            ),
            validation=ValidationResult(
                is_compliant=None,
                deviations=["Unknown grade 'MYSTERY-GRADE' - manual review required."],
                outcome="NEEDS_REVIEW",
            ),
            needs_review=True,
            row_confidence=0.6,
        )
        extraction = _make_extraction(items=[item], confidence_score=0.85, needs_review=True)
        decision = apply_review_policy(extraction, profile=_clean_profile())
        self.assertIn("unresolved_grade", decision.structured_reasons)
        # Must not emit the non-compliant token just because is_compliant is None.
        self.assertNotIn("validation_conflict:row_non_compliant", decision.structured_reasons)

    def test_unresolved_stainless_spec_emits_unresolved_spec_token(self):
        item = ExtractedItem(
            item_id="1",
            heat_number="H1",
            grade="1.4301",
            weight_or_length="100 kg",
            mechanical_properties=MechanicalProperties(
                yield_strength_mpa=220.0,
                tensile_strength_mpa=520.0,
                elongation_percentage=45.0,
            ),
            validation=ValidationResult(
                is_compliant=None,
                deviations=["Grade '1.4301' recognised but no spec is declared - manual review required."],
                outcome="UNRESOLVED_SPEC",
            ),
            needs_review=True,
            row_confidence=0.8,
        )
        extraction = _make_extraction(items=[item], confidence_score=0.85, needs_review=True)
        decision = apply_review_policy(extraction, profile=_clean_profile())
        self.assertIn("unresolved_spec", decision.structured_reasons)
        self.assertNotIn("validation_conflict:row_non_compliant", decision.structured_reasons)

    def test_unsupported_spec_family_is_explicitly_reported(self):
        item = ExtractedItem(
            item_id="1",
            heat_number="H1",
            grade="304",
            weight_or_length="100 kg",
            mechanical_properties=MechanicalProperties(
                yield_strength_mpa=220.0,
                tensile_strength_mpa=520.0,
                elongation_percentage=45.0,
            ),
            validation=ValidationResult(
                is_compliant=None,
                deviations=["Grade family '304' is recognised but not covered by deterministic rules."],
                outcome="UNSUPPORTED_SPEC_FAMILY",
            ),
            needs_review=True,
            row_confidence=0.8,
        )
        extraction = _make_extraction(items=[item], confidence_score=0.8, needs_review=True)
        decision = apply_review_policy(extraction, profile=_clean_profile())
        self.assertIn("unsupported_spec_family", decision.structured_reasons)

    def test_numeric_uncertain_is_promoted_to_structured_token(self):
        item = ExtractedItem(
            item_id="1",
            heat_number="H1",
            grade="S355J2",
            weight_or_length="100 kg",
            mechanical_properties=MechanicalProperties(
                yield_strength_mpa=400.0,
                tensile_strength_mpa=520.0,
                elongation_percentage=24.0,
            ),
            validation=ValidationResult(
                is_compliant=True,
                deviations=[],
                outcome="RESOLVED_COMPLIANT",
            ),
            row_confidence=0.9,
        )
        extraction = _make_extraction(
            items=[item],
            confidence_score=0.85,
            review_reasons=["numeric_uncertain:yield_strength_mpa"],
        )
        decision = apply_review_policy(extraction, profile=_clean_profile())
        self.assertIn("numeric_uncertain:yield_strength_mpa", decision.structured_reasons)

    def test_preserves_existing_reasons(self):
        items = [
            ExtractedItem(
                item_id="1",
                heat_number="H1",
                grade="S355J2",
                weight_or_length="100 kg",
                mechanical_properties=MechanicalProperties(
                    yield_strength_mpa=400.0,
                    tensile_strength_mpa=520.0,
                    elongation_percentage=24.0,
                ),
                row_confidence=0.9,
            ),
        ]
        extraction = _make_extraction(
            items=items,
            confidence_score=0.8,
            review_reasons=["prior custom reason"],
        )
        decision = apply_review_policy(extraction, profile=_clean_profile())
        self.assertIn("prior custom reason", extraction.review_reasons)
        # No structured tokens are expected for a fully-clean record, so
        # needs_review should reflect only the pre-existing reason.
        self.assertTrue(decision.review_required)


if __name__ == "__main__":
    unittest.main()
