from __future__ import annotations

import unittest

from app.domain.labeled_identifier_extractor import (
    apply_labeled_identifiers,
    extract_labeled_identifiers_from_text,
)
from app.schemas.extraction import ExtractedItem, MechanicalProperties, UniversalDocumentExtraction
from app.services.traceability import TRACEABILITY_UNVERIFIED, validate_traceability


class LabeledIdentifierExtractorTests(unittest.TestCase):
    def test_extract_cast_number_from_labeled_text(self):
        matches = extract_labeled_identifiers_from_text("CAST NO: 9316704")
        self.assertEqual(len(matches), 1)
        field, label, value = matches[0]
        self.assertEqual(field, "cast_number")
        self.assertEqual(label.upper(), "CAST NO")
        self.assertEqual(value, "9316704")

    def test_apply_to_metadata_preserves_canonical_field(self):
        metadata: dict = {"ai_analysis_remarks": "CAST NO: 9316704"}
        rows: list[dict] = [{}]
        tokens, traces = apply_labeled_identifiers(metadata, rows)
        self.assertEqual(metadata.get("cast_number"), "9316704")
        self.assertIn("cast_number:from_labeled_text:CAST NO", tokens)
        self.assertEqual(traces[0]["field"], "cast_number")
        self.assertNotEqual(metadata.get("heat_number"), "9316704")

    def test_does_not_overwrite_existing_identifier(self):
        metadata = {
            "cast_number": "EXISTING",
            "ai_analysis_remarks": "CAST NO: 9316704",
        }
        tokens, _ = apply_labeled_identifiers(metadata, [{}])
        self.assertEqual(metadata["cast_number"], "EXISTING")
        self.assertEqual(tokens, [])

    def test_traceability_keeps_review_when_confidence_is_low(self):
        metadata = {"cast_number": "9316704", "field_confidence": {"cast_number": 0.70}}
        item = ExtractedItem(
            item_id="1",
            cast_number="9316704",
            grade="S355",
            mechanical_properties=MechanicalProperties(
                yield_strength_mpa=355.0,
                tensile_strength_mpa=510.0,
                elongation_percentage=22.0,
            ),
        )
        extraction = UniversalDocumentExtraction(
            supplier_name="Supplier",
            document_type="Mill Test Certificate",
            cast_number="9316704",
            total_items_detected=1,
            items=[item],
            confidence_score=0.8,
        )
        preprocessing_meta = {
            "identifier_confidence": {
                "metadata": {"cast_number": 0.70},
                "rows": [{"cast_number": 0.70}],
            }
        }
        result = validate_traceability(extraction, preprocessing_meta)
        self.assertEqual(result.cast_number, None)
        self.assertEqual(result.traceability_status, TRACEABILITY_UNVERIFIED)
        raw_candidates = result.raw_identifier_candidates.get("cast_number")
        self.assertTrue(raw_candidates)


if __name__ == "__main__":
    unittest.main()
