from __future__ import annotations

import unittest
import sys
import types

from app.schemas.extraction import ExtractedItem, MechanicalProperties, UniversalDocumentExtraction, ValidationResult
from app.services.confidence import normalize_confidence

document_profiler_stub = types.ModuleType("app.services.document_profiler")


class DocumentProfile:
    pass


document_profiler_stub.DocumentProfile = DocumentProfile
sys.modules.setdefault("app.services.document_profiler", document_profiler_stub)

from app.services.review_policy import evaluate_review_policy


def _compliant_extraction(*, confidence_score: float = 0.95) -> UniversalDocumentExtraction:
    item = ExtractedItem(
        item_id="1",
        heat_number="H123",
        grade="S195",
        mechanical_properties=MechanicalProperties(
            yield_strength_mpa=258.0,
            tensile_strength_mpa=421.0,
            elongation_percentage=29.0,
        ),
        validation=ValidationResult(is_compliant=True, deviations=[], outcome="COMPLIANT"),
        row_confidence=0.95,
    )
    return UniversalDocumentExtraction(
        supplier_name="Supplier",
        document_type="Mill Test Certificate",
        total_items_detected=1,
        items=[item],
        confidence_score=confidence_score,
        raw_model_confidence=confidence_score,
    )


class ConservativeDecisionConfidenceTests(unittest.TestCase):
    def test_low_critical_identifier_confidence_caps_overall_decision_confidence(self):
        extraction = _compliant_extraction(confidence_score=0.96)
        assessment = normalize_confidence(
            extraction=extraction,
            preprocessing_meta={
                "identifier_guard": {
                    "events": [
                        {
                            "scope": "row",
                            "row_index": 0,
                            "suppressed_fields": ["heat_number"],
                            "suppressed_identifiers": [
                                {
                                    "field": "heat_number",
                                    "raw_candidate": "H123",
                                    "accepted_value": None,
                                    "reason": "low_identifier_confidence",
                                    "confidence": 0.62,
                                }
                            ],
                        }
                    ]
                }
            },
            raw_reported_total_items=1,
            review_confidence_threshold=0.75,
        )

        self.assertLessEqual(assessment.final_confidence, 0.70)
        self.assertEqual(
            assessment.metrics["confidence_breakdown"]["overall_decision_confidence"],
            0.70,
        )
        self.assertEqual(assessment.status, "NEEDS_REVIEW")

    def test_ambiguous_null_critical_identifier_forces_needs_review(self):
        extraction = _compliant_extraction(confidence_score=0.96)
        extraction.items[0].heat_number = None
        assessment = normalize_confidence(
            extraction=extraction,
            preprocessing_meta={
                "identifier_guard": {
                    "events": [
                        {
                            "scope": "row",
                            "row_index": 0,
                            "suppressed_fields": ["heat_number"],
                            "suppressed_identifiers": [
                                {
                                    "field": "heat_number",
                                    "raw_candidate": "H12B",
                                    "accepted_value": None,
                                    "reason": "visual_ambiguity",
                                    "confidence": 0.91,
                                }
                            ],
                        }
                    ]
                }
            },
            raw_reported_total_items=1,
            review_confidence_threshold=0.75,
        )

        self.assertEqual(assessment.status, "NEEDS_REVIEW")
        self.assertIn("critical_identifier_unverified", assessment.review_reasons)

    def test_extraction_confidence_alone_cannot_auto_accept(self):
        decision = evaluate_review_policy(
            extracted_json={
                "document_type": "Mill Test Certificate",
                "items": [
                    {
                        "heat_number": "H123",
                        "grade": "S195",
                        "mechanical_properties": {
                            "yield_strength_mpa": 258.0,
                            "tensile_strength_mpa": 421.0,
                            "elongation_percentage": 29.0,
                        },
                    }
                ],
            },
            confidence={"extraction_confidence": 0.99},
            validation_errors=[],
            document_profile={"quality_bucket": "digital_clean"},
        )

        self.assertEqual(decision["decision"], "review_required")
        self.assertIn("confidence_below_threshold", decision["review_reasons"])


if __name__ == "__main__":
    unittest.main()
