from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import json
from pathlib import Path

from app.services.extraction_pipeline import run_multi_stage_extraction
from app.services.document_profiler import DocumentProfile

class Doc008RegressionTests(unittest.TestCase):
    def setUp(self):
        # Load ground truth for doc008
        gt_path = Path("data/gold/ground_truth/doc008.json")
        if not gt_path.exists():
            self.skipTest("doc008 ground truth not found")
            
        with open(gt_path, "r", encoding="utf-8") as f:
            self.ground_truth = json.load(f)

    def _get_mock_page(self):
        page_mock = MagicMock()
        page_mock.page_number = 1
        page_mock.table_crop_available = True
        return page_mock

    def _get_mock_profile(self, *, quality_class="noisy_scan", reasons=None):
        return DocumentProfile(
            document_id="doc008",
            filename="doc008.pdf",
            page_count=1,
            has_text_layer=False,
            text_density=0.0,
            blur_score=150.0,
            noise_score=15.0,
            table_presence_hint=True,
            quality_class=quality_class,
            reasons=reasons or []
        )

    @patch("app.services.extraction_pipeline._run_metadata_extraction")
    @patch("app.services.extraction_pipeline._run_row_extraction")
    def test_doc008_no_hallucinated_heat_numbers(self, mock_row, mock_meta):
        # Setup mock metadata extraction
        mock_meta.return_value = (
            {
                "supplier_name": "NOKSEL BORU SANAYİ A.Ş.",
                "document_type": "Mill Test Certificate",
                "product_category": "PIPE",
                "certificate_date": "27.04.2011",
                "confidence_score": 0.85
            },
            {"input_tokens": 100, "output_tokens": 50}
        )
        
        # Setup mock row extraction with hallucinated heat numbers
        mock_items = []
        for gt_item in self.ground_truth["items"]:
            item = dict(gt_item)
            field_conf = {
                "yield_strength_mpa": 0.9,
                "tensile_strength_mpa": 0.9,
                "elongation_percentage": 0.9,
            }
            if item["heat_number"] is None:
                # LLM hallucination: invents a heat number
                item["heat_number"] = "10115084"
                item["needs_review"] = True
                item["visual_ambiguity"] = True  # Trigger suppression
                field_conf["heat_number"] = 0.95 
            else:
                item["needs_review"] = False
                field_conf["heat_number"] = 0.95
                
            item["row_confidence"] = 0.8
            item["field_confidence"] = field_conf
            mock_items.append(item)
            
        mock_row.return_value = (
            {"total_items_detected": len(mock_items), "items": mock_items},
            {"input_tokens": 200, "output_tokens": 100}
        )

        pages = [self._get_mock_page()]
        profile = self._get_mock_profile()
        preprocessing_meta = {"pages": [{"table_detection": {"table_found": True}}]}
        
        extraction = run_multi_stage_extraction(pages, preprocessing_meta, profile=profile)
        
        self.assertEqual(extraction.status, "NEEDS_REVIEW")
        self.assertTrue(extraction.needs_review)
        self.assertEqual(extraction.traceability_status, "UNVERIFIED")
        self.assertIn("traceability_unverified", extraction.review_reasons)
        self.assertIn("critical_identifier_unverified", extraction.review_reasons)
        
        for i, item in enumerate(extraction.items):
            if i >= 2: # Item 3, 4, 5
                self.assertIsNone(item.heat_number)
                self.assertTrue(item.needs_review)
                self.assertEqual(item.traceability_status, "UNVERIFIED")
                self.assertEqual(item.validation.outcome, "NEEDS_REVIEW")
                self.assertIn("heat_number", item.accepted_identifier_values)
                self.assertIsNone(item.accepted_identifier_values["heat_number"])
                self.assertIn("heat_number", item.raw_identifier_candidates)
            else:
                self.assertIsNotNone(item.heat_number)

    @patch("app.services.extraction_pipeline._run_metadata_extraction")
    @patch("app.services.extraction_pipeline._run_row_extraction")
    def test_heat_number_preservation_on_unrelated_review(self, mock_row, mock_meta):
        """needs_review=true due to unresolved_spec should preserve high-confidence heat_number."""
        mock_meta.return_value = ({}, {"input_tokens": 0, "output_tokens": 0})
        
        item = {
            "item_id": "1",
            "heat_number": "H123",
            "mechanical_properties": {"yield_strength_mpa": 400},
            "needs_review": True,
            "review_reasons": ["unresolved_spec"],
            "field_confidence": {"heat_number": 0.9},
            "row_confidence": 0.9
        }
        mock_row.return_value = ({"total_items_detected": 1, "items": [item]}, {"input_tokens": 0, "output_tokens": 0})
        
        extraction = run_multi_stage_extraction([self._get_mock_page()], {}, profile=self._get_mock_profile())
        
        self.assertEqual(extraction.items[0].heat_number, "H123")
        self.assertTrue(extraction.items[0].needs_review)

    @patch("app.services.extraction_pipeline._run_metadata_extraction")
    @patch("app.services.extraction_pipeline._run_row_extraction")
    def test_heat_number_suppression_on_visual_ambiguity(self, mock_row, mock_meta):
        """needs_review=true due to visual_ambiguity should null heat_number."""
        mock_meta.return_value = ({}, {"input_tokens": 0, "output_tokens": 0})
        
        item = {
            "item_id": "1",
            "heat_number": "H123",
            "visual_ambiguity": True,
            "field_confidence": {"heat_number": 0.9},
            "row_confidence": 0.9
        }
        mock_row.return_value = ({"total_items_detected": 1, "items": [item]}, {"input_tokens": 0, "output_tokens": 0})
        
        extraction = run_multi_stage_extraction([self._get_mock_page()], {}, profile=self._get_mock_profile())
        
        self.assertIsNone(extraction.items[0].heat_number)

    @patch("app.services.extraction_pipeline._run_metadata_extraction")
    @patch("app.services.extraction_pipeline._run_row_extraction")
    def test_heat_number_suppression_on_low_confidence(self, mock_row, mock_meta):
        """low heat_number confidence should null heat_number."""
        mock_meta.return_value = ({}, {"input_tokens": 0, "output_tokens": 0})
        
        item = {
            "item_id": "1",
            "heat_number": "H123",
            "field_confidence": {"heat_number": 0.79},
            "row_confidence": 0.9
        }
        mock_row.return_value = ({"total_items_detected": 1, "items": [item]}, {"input_tokens": 0, "output_tokens": 0})
        
        extraction = run_multi_stage_extraction([self._get_mock_page()], {}, profile=self._get_mock_profile())
        
        self.assertIsNone(extraction.items[0].heat_number)

    @patch("app.services.extraction_pipeline._run_metadata_extraction")
    @patch("app.services.extraction_pipeline._run_row_extraction")
    def test_heat_number_suppression_on_review_reasons(self, mock_row, mock_meta):
        """Suppress heat_number if item_raw.review_reasons contains specific tokens."""
        mock_meta.return_value = ({}, {"input_tokens": 0, "output_tokens": 0})
        
        reasons_to_test = [
            "ambiguous_identifier",
            "low_identifier_confidence",
            "heat_number_uncertain",
            "weak_heat_number_evidence"
        ]
        
        for reason in reasons_to_test:
            item = {
                "item_id": "1",
                "heat_number": "H123",
                "review_reasons": [reason],
                "field_confidence": {"heat_number": 0.9},
                "row_confidence": 0.9
            }
            mock_row.return_value = ({"total_items_detected": 1, "items": [item]}, {"input_tokens": 0, "output_tokens": 0})
            
            extraction = run_multi_stage_extraction([self._get_mock_page()], {}, profile=self._get_mock_profile())
            self.assertIsNone(extraction.items[0].heat_number, f"Failed for reason: {reason}")

    @patch("app.services.extraction_pipeline._run_metadata_extraction")
    @patch("app.services.extraction_pipeline._run_row_extraction")
    def test_low_identifier_legibility_suppresses_metadata_identifiers_only(self, mock_row, mock_meta):
        """Certificate/order candidates stay in evidence; mechanical values remain accepted."""
        mock_meta.return_value = (
            {
                "supplier_name": "NOKSEL BORU SANAYI A.S.",
                "document_type": "Mill Test Certificate",
                "product_category": "PIPE",
                "certificate_number": "CERT-88B",
                "order_number": "ORD-1009",
                "field_confidence": {"certificate_number": 0.55, "order_number": 0.52},
                "confidence_score": 0.9,
            },
            {"input_tokens": 0, "output_tokens": 0},
        )
        item = {
            "item_id": "1",
            "heat_number": "H123",
            "grade": "S195",
            "mechanical_properties": {
                "yield_strength_mpa": 264,
                "tensile_strength_mpa": 418,
                "elongation_percentage": 34,
            },
            "field_confidence": {"heat_number": 0.95, "item_id": 0.95},
            "row_confidence": 0.95,
        }
        mock_row.return_value = ({"total_items_detected": 1, "items": [item]}, {"input_tokens": 0, "output_tokens": 0})

        extraction = run_multi_stage_extraction(
            [self._get_mock_page()],
            {},
            profile=self._get_mock_profile(quality_class="scan_clean", reasons=["low_identifier_legibility"]),
        )

        self.assertEqual(extraction.items[0].mechanical_properties.yield_strength_mpa, 264)
        self.assertEqual(extraction.items[0].mechanical_properties.tensile_strength_mpa, 418)
        self.assertEqual(extraction.items[0].mechanical_properties.elongation_percentage, 34)
        self.assertIn("critical_identifier_unverified", extraction.review_reasons)
        self.assertIn("traceability_unverified", extraction.review_reasons)
        guard_events = extraction.explanation["identifier_guard"]["events"]
        metadata_event = next(event for event in guard_events if event["scope"] == "metadata")
        self.assertIn("certificate_number", metadata_event["suppressed_fields"])
        self.assertIn("order_number", metadata_event["suppressed_fields"])
        raw_candidates = {
            event["field"]: event["raw_candidate"]
            for event in metadata_event["suppressed_identifiers"]
        }
        self.assertEqual(raw_candidates["certificate_number"], "CERT-88B")
        self.assertEqual(raw_candidates["order_number"], "ORD-1009")
        self.assertEqual(extraction.traceability_status, "VERIFIED")
        self.assertEqual(extraction.items[0].heat_number, "H123")
        self.assertIn("certificate_number", extraction.raw_identifier_candidates)
        self.assertIn("order_number", extraction.raw_identifier_candidates)
        self.assertIn("certificate_number", extraction.accepted_identifier_values)
        self.assertIsNone(extraction.accepted_identifier_values["certificate_number"])
        self.assertIn("order_number", extraction.accepted_identifier_values)
        self.assertIsNone(extraction.accepted_identifier_values["order_number"])

if __name__ == "__main__":
    unittest.main()
