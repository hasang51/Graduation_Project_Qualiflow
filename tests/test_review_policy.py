from __future__ import annotations

import unittest

from app.schemas.extraction import (
    ExtractedItem,
    MechanicalProperties,
    UniversalDocumentExtraction,
    ValidationResult,
)
from app.services.document_profiler import DocumentProfile
from app.services.review_policy import apply_review_policy, evaluate_review_policy


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
        quality_class="noisy_scan",
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
    def test_deterministic_policy_auto_accepts_clean_supported_document(self):
        decision = evaluate_review_policy(
            extracted_json={
                "document_type": "Mill Test Certificate",
                "items": [
                    {
                        "heat_number": "H1",
                        "grade": "S355J2",
                        "mechanical_properties": {
                            "yield_strength_mpa": 380.0,
                            "tensile_strength_mpa": 500.0,
                            "elongation_percentage": 25.0,
                        },
                    }
                ],
            },
            confidence={
                "field_confidences": {
                    "heat_number": 0.95,
                    "grade": 0.94,
                    "yield_strength_mpa": 0.93,
                    "tensile_strength_mpa": 0.92,
                    "elongation_percentage": 0.91,
                }
            },
            validation_errors=[],
            document_profile={"quality_bucket": "clean_scan"},
        )
        self.assertEqual(decision["decision"], "auto_accept")
        self.assertEqual(decision["review_reasons"], [])
        self.assertEqual(decision["blocking_errors"], [])

    def test_deterministic_policy_blocks_severe_scan_even_with_complete_fields(self):
        decision = evaluate_review_policy(
            extracted_json={
                "document_type": "Certificate of Analysis",
                "heat_number": "H1",
                "grade": "S355J2",
                "yield_strength_mpa": 380.0,
                "tensile_strength_mpa": 500.0,
                "elongation_percentage": 25.0,
            },
            confidence=0.95,
            validation_errors=[],
            document_profile={"quality_bucket": "severe_scan"},
        )
        self.assertEqual(decision["decision"], "review_required")
        self.assertIn("quality_blocker:severe_scan", decision["review_reasons"])
        blockers = [*decision["blocking_errors"], *decision["blocking_reasons"]]
        self.assertIn("quality_blocker:severe_scan", blockers)

    def test_deterministic_policy_never_accepts_missing_critical_fields(self):
        decision = evaluate_review_policy(
            extracted_json={
                "document_type": "Mill Test Certificate",
                "items": [
                    {
                        "heat_number": "H1",
                        "mechanical_properties": {
                            "yield_strength_mpa": 380.0,
                            "tensile_strength_mpa": 500.0,
                            "elongation_percentage": 25.0,
                        },
                    }
                ],
            },
            confidence=0.95,
            validation_errors=[],
            document_profile={"quality_bucket": "digital_pdf"},
        )
        self.assertEqual(decision["decision"], "review_required")
        self.assertIn("missing_critical_field:grade", decision["review_reasons"])

    def test_deterministic_policy_blocks_low_critical_confidence(self):
        decision = evaluate_review_policy(
            extracted_json={
                "document_type": "Mill Test Certificate",
                "heat_number": "H1",
                "grade": "S355J2",
                "yield_strength_mpa": 380.0,
                "tensile_strength_mpa": 500.0,
                "elongation_percentage": 25.0,
            },
            confidence={
                "field_confidences": {
                    "heat_number": 0.95,
                    "grade": 0.79,
                    "yield_strength_mpa": 0.91,
                    "tensile_strength_mpa": 0.91,
                    "elongation_percentage": 0.91,
                }
            },
            validation_errors=[],
            document_profile={"quality_bucket": "digital_pdf"},
        )
        self.assertEqual(decision["decision"], "review_required")
        self.assertIn("confidence_below_threshold", decision["review_reasons"])
        self.assertEqual(decision["confidence_summary"]["min_critical_field_confidence"], 0.79)

    def test_deterministic_policy_never_accepts_unsupported_document_type(self):
        decision = evaluate_review_policy(
            extracted_json={
                "document_type": "Invoice",
                "heat_number": "H1",
                "grade": "S355J2",
                "yield_strength_mpa": 380.0,
                "tensile_strength_mpa": 500.0,
                "elongation_percentage": 25.0,
            },
            confidence=0.95,
            validation_errors=[],
            document_profile={"quality_bucket": "digital_pdf"},
        )
        self.assertEqual(decision["decision"], "review_required")
        self.assertIn("unsupported_document_type", decision["review_reasons"])

    def test_deterministic_policy_routes_blocking_validation_errors_to_review(self):
        decision = evaluate_review_policy(
            extracted_json={
                "document_type": "Mill Test Certificate",
                "heat_number": "H1",
                "grade": "S355J2",
                "yield_strength_mpa": 380.0,
                "tensile_strength_mpa": 500.0,
                "elongation_percentage": 25.0,
            },
            confidence=0.95,
            validation_errors=[{"code": "schema_violation", "blocking": True}],
            document_profile={"quality_bucket": "digital_pdf"},
        )
        self.assertEqual(decision["decision"], "review_required")
        self.assertIn("validation_blocking_error", decision["review_reasons"])
        self.assertEqual(decision["blocking_errors"], ["schema_violation"])

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

    def test_degraded_document_does_not_emit_document_quality_token(self):
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
        self.assertNotIn("document_quality:noisy_scan", decision.structured_reasons)
        self.assertIn("confidence_below_threshold", decision.structured_reasons)

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

    def test_missing_critical_identifier_group_when_none_present(self):
        items = [
            ExtractedItem(
                item_id=None,
                pipe_id=None,
                heat_number=None,
                batch_number=None,
                lot_number=None,
                colata_number=None,
                cast_number=None,
                charge_number=None,
                coil_number=None,
                grade="S355J2",
                mechanical_properties=MechanicalProperties(
                    yield_strength_mpa=355.0,
                    tensile_strength_mpa=510.0,
                    elongation_percentage=24.0,
                ),
                validation=ValidationResult(is_compliant=True, deviations=[], outcome="COMPLIANT"),
            )
        ]
        extraction = _make_extraction(items=items)
        decision = apply_review_policy(extraction, profile=_clean_profile())
        self.assertIn("missing_critical_identifier_group", decision.structured_reasons)

    def test_does_not_emit_missing_heat_when_batch_exists(self):
        items = [
            ExtractedItem(
                item_id=None,
                heat_number=None,
                batch_number="410537",
                grade="S355J2",
                mechanical_properties=MechanicalProperties(
                    yield_strength_mpa=355.0,
                    tensile_strength_mpa=510.0,
                    elongation_percentage=24.0,
                ),
                validation=ValidationResult(is_compliant=True, deviations=[], outcome="COMPLIANT"),
                accepted_identifier_values={"batch_number": "410537", "traceability_identifier_value": "410537"},
            )
        ]
        extraction = _make_extraction(items=items)
        decision = apply_review_policy(extraction, profile=_clean_profile())
        self.assertNotIn("missing_critical_field:heat_number", decision.structured_reasons)

    def test_missing_grade_emits_missing_critical_field_token(self):
        item = ExtractedItem(
            item_id="1",
            heat_number="H1",
            grade=None,
            weight_or_length="100 kg",
            mechanical_properties=MechanicalProperties(
                yield_strength_mpa=380.0,
                tensile_strength_mpa=500.0,
                elongation_percentage=25.0,
            ),
            validation=ValidationResult(
                is_compliant=None,
                deviations=["Grade is missing from the extracted row - manual review required."],
                outcome="MISSING_CRITICAL_FIELD_GRADE",
            ),
            needs_review=True,
            row_confidence=0.6,
        )
        extraction = _make_extraction(items=[item], confidence_score=0.85, needs_review=True)
        decision = apply_review_policy(extraction, profile=_clean_profile())
        self.assertIn("missing_critical_field:grade", decision.structured_reasons)
        self.assertNotIn("unresolved_grade", decision.structured_reasons)
        self.assertNotIn("validation_conflict:row_non_compliant", decision.structured_reasons)

    def test_explicit_unmapped_grade_does_not_emit_unresolved_grade(self):
        item = ExtractedItem(
            item_id="1",
            heat_number="H1",
            grade="MYSTERY-GRADE",
            grade_provenance="labeled_field",
            weight_or_length="100 kg",
            mechanical_properties=MechanicalProperties(
                yield_strength_mpa=380.0,
                tensile_strength_mpa=500.0,
                elongation_percentage=25.0,
            ),
            validation=ValidationResult(
                is_compliant=None,
                deviations=[
                    "Grade 'MYSTERY-GRADE' is explicitly stated but not mapped in the internal catalog - manual review required."
                ],
                outcome="EXPLICIT_UNMAPPED_GRADE",
            ),
            needs_review=True,
            row_confidence=0.6,
        )
        extraction = _make_extraction(
            items=[item],
            confidence_score=0.85,
            needs_review=True,
            review_reasons=["explicit_unmapped_grade"],
        )
        decision = apply_review_policy(extraction, profile=_clean_profile())
        self.assertNotIn("unresolved_grade", decision.structured_reasons)
        self.assertIn("explicit_unmapped_grade", decision.structured_reasons)
        self.assertNotIn("unsupported_spec_family", decision.structured_reasons)
        self.assertTrue(decision.review_required)

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
                yield_strength_mpa=70.0,
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

    def test_doc008_identifier_uncertainty_beats_high_confidence_compliance(self):
        items = [
            ExtractedItem(
                item_id="1",
                heat_number="10115084",
                grade="S195",
                weight_or_length="126,9 x 2.60 mm",
                mechanical_properties=MechanicalProperties(
                    yield_strength_mpa=264.0,
                    tensile_strength_mpa=418.0,
                    elongation_percentage=34.0,
                ),
                validation=ValidationResult(is_compliant=True, deviations=[], outcome="COMPLIANT"),
                needs_review=False,
                row_confidence=0.95,
            ),
            ExtractedItem(
                item_id=None,
                heat_number=None,
                grade="S195",
                weight_or_length="126,9 x 2.60 mm",
                mechanical_properties=MechanicalProperties(
                    yield_strength_mpa=258.0,
                    tensile_strength_mpa=421.0,
                    elongation_percentage=29.0,
                ),
                validation=ValidationResult(is_compliant=True, deviations=[], outcome="COMPLIANT"),
                needs_review=True,
                row_confidence=0.95,
            ),
        ]
        extraction = _make_extraction(
            items=items,
            confidence_score=0.95,
            needs_review=True,
            review_reasons=["critical_identifier_unverified"],
            status="COMPLETED",
        )

        decision = apply_review_policy(
            extraction,
            profile=_degraded_profile(),
            preprocessing_meta={
                "identifier_guard": {
                    "events": [
                        {
                            "row_index": 1,
                            "suppressed_fields": ["heat_number"],
                            "suppressed_identifiers": [
                                {
                                    "field": "heat_number",
                                    "raw_candidate": "10115084",
                                    "accepted_value": None,
                                    "evidence_note": "Suppressed heat_number candidate.",
                                }
                            ],
                        }
                    ]
                }
            },
        )

        self.assertTrue(decision.review_required)
        self.assertTrue(extraction.needs_review)
        self.assertEqual(extraction.status, "NEEDS_REVIEW")
        self.assertIn("critical_identifier_unverified", decision.structured_reasons)
        self.assertIn("traceability_unverified", decision.structured_reasons)


if __name__ == "__main__":
    unittest.main()
