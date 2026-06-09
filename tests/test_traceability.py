from __future__ import annotations

import unittest

from app.schemas.extraction import ExtractedItem, MechanicalProperties, UniversalDocumentExtraction, ValidationResult
from app.services.traceability import (
    TRACEABILITY_REVIEW_REASON,
    TRACEABILITY_UNVERIFIED,
    TRACEABILITY_VERIFIED,
    apply_traceability_remarks,
    compose_traceability_remarks,
    sanitize_unverified_traceability_for_user,
    validate_traceability,
)


def _mechanically_compliant_item(**overrides) -> ExtractedItem:
    values = {
        "item_id": "ITEM-1",
        "heat_number": "H-123",
        "grade": "S195",
        "mechanical_properties": MechanicalProperties(
            yield_strength_mpa=264.0,
            tensile_strength_mpa=418.0,
            elongation_percentage=34.0,
        ),
        "validation": ValidationResult(is_compliant=True, deviations=[], outcome="COMPLIANT"),
        "row_confidence": 0.95,
    }
    values.update(overrides)
    return ExtractedItem(**values)


def _extraction(item: ExtractedItem, **overrides) -> UniversalDocumentExtraction:
    values = {
        "supplier_name": "Supplier",
        "document_type": "Mill Test Certificate",
        "product_category": "PIPE",
        "batch_number": "B-100",
        "certificate_number": "CERT-200",
        "order_number": "ORD-300",
        "total_items_detected": 1,
        "items": [item],
        "confidence_score": 0.95,
        "raw_model_confidence": 0.95,
        "is_compliant": True,
        "outcome": "COMPLIANT",
        "status": "COMPLETED",
    }
    values.update(overrides)
    return UniversalDocumentExtraction(**values)


def _verified_confidence_meta() -> dict:
    return {
        "identifier_confidence": {
            "metadata": {
                "batch_number": 0.95,
                "certificate_number": 0.96,
                "order_number": 0.97,
            },
            "rows": [
                {
                    "heat_number": 0.94,
                    "item_id": 0.93,
                }
            ],
        }
    }


class TraceabilityValidationTests(unittest.TestCase):
    def test_all_five_identifiers_verified_keeps_mechanical_compliance(self):
        extraction = validate_traceability(
            _extraction(_mechanically_compliant_item()),
            _verified_confidence_meta(),
        )

        self.assertEqual(extraction.traceability_status, TRACEABILITY_VERIFIED)
        self.assertEqual(extraction.items[0].traceability_status, TRACEABILITY_VERIFIED)
        self.assertEqual(extraction.outcome, "COMPLIANT")
        self.assertTrue(extraction.is_compliant)
        self.assertNotIn(TRACEABILITY_REVIEW_REASON, extraction.review_reasons)

    def test_missing_identifier_group_downgrades_mechanical_pass_to_review(self):
        extraction = validate_traceability(
            _extraction(
                _mechanically_compliant_item(heat_number=None, batch_number=None, item_id=None),
                batch_number=None,
            ),
            _verified_confidence_meta(),
        )

        item = extraction.items[0]
        self.assertEqual(item.traceability_status, TRACEABILITY_UNVERIFIED)
        self.assertEqual(item.validation.outcome, "NEEDS_REVIEW")
        self.assertIsNone(item.validation.is_compliant)
        self.assertEqual(extraction.outcome, "NEEDS_REVIEW")
        self.assertIsNone(extraction.is_compliant)
        self.assertIn(TRACEABILITY_REVIEW_REASON, extraction.review_reasons)

    def test_verified_batch_number_keeps_row_visible_when_heat_is_null(self):
        extraction = validate_traceability(
            _extraction(
                _mechanically_compliant_item(
                    heat_number=None,
                    batch_number="410537",
                    traceability_identifier_label="COLATA/BATCH n°",
                    traceability_identifier_type="batch_number",
                ),
                batch_number="410537",
            ),
            _verified_confidence_meta(),
        )
        item = extraction.items[0]
        self.assertEqual(item.traceability_status, TRACEABILITY_VERIFIED)
        self.assertEqual(item.traceability_identifier_value, "410537")
        self.assertEqual(item.traceability_identifier_type, "batch_number")
        self.assertEqual(item.traceability_identifier_label, "COLATA/BATCH n°")
        self.assertIsNone(item.heat_number)
        self.assertEqual(item.batch_number, "410537")
        self.assertEqual(item.accepted_identifier_values["traceability_identifier_value"], "410537")
        self.assertEqual(item.accepted_identifier_values["batch_number"], "410537")

    def test_low_confidence_candidate_is_raw_only_not_accepted(self):
        meta = _verified_confidence_meta()
        meta["identifier_confidence"]["rows"][0]["heat_number"] = 0.42
        extraction = validate_traceability(
            _extraction(
                _mechanically_compliant_item(heat_number="H-AMB", batch_number=None, item_id=None),
                batch_number=None,
            ),
            meta,
        )

        item = extraction.items[0]
        self.assertIn("heat_number", item.accepted_identifier_values)
        self.assertIsNone(item.accepted_identifier_values["heat_number"])
        self.assertEqual(item.raw_identifier_candidates["heat_number"][0]["value"], "H-AMB")
        self.assertEqual(item.raw_identifier_candidates["heat_number"][0]["reason"], "low_identifier_confidence")
        self.assertEqual(item.validation.outcome, "NEEDS_REVIEW")

    def test_candidate_suppression_event_is_retained_for_debugging(self):
        meta = _verified_confidence_meta()
        meta["identifier_guard"] = {
            "events": [
                {
                    "scope": "row",
                    "row_index": 0,
                    "suppressed_fields": ["heat_number"],
                    "suppressed_identifiers": [
                        {
                            "scope": "row",
                            "row_index": 0,
                            "field": "heat_number",
                            "raw_candidate": "H-AMB",
                            "accepted_value": None,
                            "reason": "visual_ambiguity",
                            "confidence": 0.91,
                        }
                    ],
                }
            ]
        }
        extraction = validate_traceability(
            _extraction(_mechanically_compliant_item(heat_number=None)),
            meta,
        )

        item = extraction.items[0]
        self.assertIn("heat_number", item.accepted_identifier_values)
        self.assertIsNone(item.accepted_identifier_values["heat_number"])
        self.assertEqual(item.raw_identifier_candidates["heat_number"][0]["value"], "H-AMB")
        self.assertEqual(item.raw_identifier_candidates["heat_number"][0]["reason"], "visual_ambiguity")

    def test_mechanical_non_compliance_is_not_rewritten_by_traceability(self):
        item = _mechanically_compliant_item(
            heat_number=None,
            validation=ValidationResult(
                is_compliant=False,
                deviations=["Yield below minimum."],
                outcome="NON_COMPLIANT",
            ),
        )
        extraction = validate_traceability(
            _extraction(item, is_compliant=False, outcome="NON_COMPLIANT", batch_number=None),
            _verified_confidence_meta(),
        )

        self.assertEqual(extraction.traceability_status, TRACEABILITY_UNVERIFIED)
        self.assertEqual(extraction.items[0].validation.outcome, "NON_COMPLIANT")
        self.assertFalse(extraction.items[0].validation.is_compliant)
        self.assertEqual(extraction.outcome, "NON_COMPLIANT")
        self.assertFalse(extraction.is_compliant)
        self.assertNotIn(TRACEABILITY_REVIEW_REASON, extraction.review_reasons)

    def test_generic_occlusion_row_sanitizer_suppresses_identifier_only(self):
        payload = {
            "items": [
                {
                    "heat_number": "12345678",
                    "grade": "S195",
                    "mechanical_properties": {"yield_strength_mpa": 264, "tensile_strength_mpa": 418},
                    "row_status": "NEEDS_REVIEW",
                    "review_reasons": ["critical_identifier_unverified"],
                }
            ]
        }

        sanitize_unverified_traceability_for_user(payload)
        row = payload["items"][0]

        self.assertIsNone(row["heat_number"])
        self.assertEqual(row["raw_identifier_candidates"]["heat_number"], "12345678")
        self.assertIsNone(row["accepted_identifier_values"]["heat_number"])
        self.assertEqual(row["mechanical_properties"]["yield_strength_mpa"], 264)
        self.assertEqual(row["mechanical_properties"]["tensile_strength_mpa"], 418)

    def test_doc001_readable_identifier_stays_visible_with_unresolved_spec(self):
        payload = {
            "items": [
                {
                    "heat_number": None,
                    "batch_number": "410537",
                    "traceability_identifier_value": "410537",
                    "grade": "S195",
                    "mechanical_properties": {"yield_strength_mpa": 264, "tensile_strength_mpa": 418},
                    "row_status": "NEEDS_REVIEW",
                    "review_reasons": ["unresolved_spec"],
                    "identifier_visibility_verified": True,
                    "accepted_identifier_values": {
                        "heat_number": None,
                        "batch_number": "410537",
                        "traceability_identifier_value": "410537",
                    },
                }
            ]
        }

        sanitize_unverified_traceability_for_user(payload)
        row = payload["items"][0]

        self.assertEqual(row["batch_number"], "410537")
        self.assertEqual(row["accepted_identifier_values"]["batch_number"], "410537")
        self.assertEqual(row["accepted_identifier_values"]["traceability_identifier_value"], "410537")
        self.assertEqual(row["mechanical_properties"]["yield_strength_mpa"], 264)

    def test_sanitizer_suppresses_unverified_raw_candidate(self):
        payload = {
            "items": [
                {
                    "batch_number": "A-raw",
                    "row_status": "NEEDS_REVIEW",
                    "review_reasons": ["critical_identifier_unverified"],
                    "identifier_visibility_verified": False,
                    "accepted_identifier_values": {
                        "batch_number": None,
                        "traceability_identifier_value": None,
                    },
                    "raw_identifier_candidates": {"batch_number": "A-raw"},
                }
            ]
        }
        sanitize_unverified_traceability_for_user(payload)
        row = payload["items"][0]
        self.assertIsNone(row["batch_number"])
        self.assertIsNone(row["accepted_identifier_values"]["batch_number"])


class ComposeTraceabilityRemarksTests(unittest.TestCase):
    def test_primary_identifier_with_secondary_candidates(self):
        payload = {
            "traceability_identifier_type": "batch_number",
            "traceability_identifier_label": "COLATA/BATCH n°",
            "traceability_identifier_value": "410537",
            "raw_identifier_candidates": {
                "heat_number": [{"value": "410537", "reason": "low_identifier_confidence"}],
                "certificate_number": "CERT-99",
            },
        }
        remarks = compose_traceability_remarks(payload)
        self.assertIn("Primary traceability identifier COLATA/BATCH n° 410537", remarks)
        self.assertIn("Secondary identifier candidates: CERTIFICATE NUMBER CERT-99", remarks)
        self.assertNotIn("HEAT NO 410537", remarks or "")

    def test_apply_remarks_replaces_conflicting_llm_identifier_claim(self):
        payload = {
            "ai_analysis_remarks": "Heat number H-OLD was extracted from the certificate.",
            "traceability_identifier_type": "batch_number",
            "traceability_identifier_label": "COLATA/BATCH n°",
            "traceability_identifier_value": "410537",
        }
        apply_traceability_remarks(payload)
        remarks = payload["ai_analysis_remarks"]
        self.assertIn("Primary traceability identifier COLATA/BATCH n° 410537", remarks)
        self.assertNotIn("Heat number H-OLD", remarks)

    def test_unverified_block_does_not_name_primary_identifier(self):
        payload = {
            "review_reasons": ["traceability_unverified"],
            "traceability_identifier_value": None,
        }
        remarks = compose_traceability_remarks(payload)
        self.assertIn("traceability-critical identifiers could not be verified", remarks)


if __name__ == "__main__":
    unittest.main()
