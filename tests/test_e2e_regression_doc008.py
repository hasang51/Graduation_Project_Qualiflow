from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import shutil
import os

from app.services.document_profiler import profile_document
from app.services.extraction_router import choose_route
from app.services.preprocessing import preprocess_pdf
from app.services.extraction_pipeline import run_multi_stage_extraction
from app.schemas.extraction import UniversalDocumentExtraction

class Doc008E2ERegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdf_path = Path("data/eval_docs/doc008.pdf")
        cls.artifact_dir = Path("tests/artifacts/doc008_e2e")
        if cls.artifact_dir.exists():
            shutil.rmtree(cls.artifact_dir)
        cls.artifact_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if cls.artifact_dir.exists():
            shutil.rmtree(cls.artifact_dir)

    def test_doc008_pipeline_regression(self):
        """End-to-end regression test for doc008 using the actual PDF and mocked LLM calls."""
        if not self.pdf_path.exists():
            self.skipTest("doc008.pdf not found")

        # 1. Profile and Route
        profile = profile_document(self.pdf_path)
        route_decision = choose_route(profile)
        
        self.assertEqual(profile.quality_class, "noisy_scan")
        self.assertEqual(route_decision.selected_route, "path_c_noisy_scan")

        # 2. Preprocess (Actually runs poppler/opencv)
        processed_pages, pre_meta = preprocess_pdf(
            str(self.pdf_path),
            artifact_dir=self.artifact_dir,
            route=route_decision.runtime_route
        )
        
        self.assertGreater(len(processed_pages), 0)
        preprocessing_meta = {
            "profile": profile.to_dict(),
            "route_decision": route_decision.to_dict(),
            **pre_meta
        }

        # 3. Mock LLM Responses for doc008
        mock_metadata = {
            "supplier_name": "NOKSEL BORU SANAYİ A.Ş.",
            "document_type": "Mill Test Certificate",
            "product_category": "PIPE",
            "certificate_date": "27.04.2011",
            "confidence_score": 0.9,
        }

        # Simulate 5 items: 2 clean, 3 ambiguous/noisy
        mock_items_payload = {
            "total_items_detected": 5,
            "items": [
                {
                    "item_id": "1",
                    "heat_number": "10115084",
                    "grade": "S195",
                    "mechanical_properties": {"yield_strength_mpa": 264, "tensile_strength_mpa": 418, "elongation_percentage": 34},
                    "row_confidence": 0.95,
                    "visual_ambiguity": True,
                    "review_reasons": ["critical_identifier_unverified"],
                    "field_confidence": {"heat_number": 0.62}
                },
                {
                    "item_id": "2",
                    "heat_number": "10110701",
                    "grade": "S195",
                    "mechanical_properties": {"yield_strength_mpa": 252, "tensile_strength_mpa": 422, "elongation_percentage": 32},
                    "row_confidence": 0.92,
                    "visual_ambiguity": True,
                    "review_reasons": ["critical_identifier_unverified"],
                    "field_confidence": {"heat_number": 0.6}
                },
                {
                    "item_id": "3",
                    "heat_number": "88888888", # Ambiguous, should be nulled
                    "grade": "S195",
                    "mechanical_properties": {"yield_strength_mpa": 258, "tensile_strength_mpa": 421, "elongation_percentage": 29},
                    "row_confidence": 0.5,
                    "visual_ambiguity": True,
                    "review_reasons": ["low_identifier_confidence"],
                    "field_confidence": {"heat_number": 0.6}
                },
                {
                    "item_id": "4",
                    "heat_number": "99999999", # Noisy, should be nulled
                    "grade": "S195",
                    "mechanical_properties": {"yield_strength_mpa": 257, "tensile_strength_mpa": 424, "elongation_percentage": 27},
                    "row_confidence": 0.4,
                    "review_reasons": ["heat_number_uncertain"],
                    "field_confidence": {"heat_number": 0.45}
                },
                {
                    "item_id": "5",
                    "heat_number": "00000000", # Missing in GT, simulated as weak evidence
                    "grade": "S195",
                    "mechanical_properties": {"yield_strength_mpa": 263, "tensile_strength_mpa": 423, "elongation_percentage": 33},
                    "row_confidence": 0.45,
                    "review_reasons": ["weak_heat_number_evidence"],
                    "field_confidence": {"heat_number": 0.5}
                }
            ]
        }

        with patch("app.services.extraction_pipeline._run_metadata_extraction") as mock_meta_call, \
             patch("app.services.extraction_pipeline._run_row_extraction") as mock_row_call:
            
            mock_meta_call.return_value = (mock_metadata, {"input_tokens": 100, "output_tokens": 50})
            mock_row_call.return_value = (mock_items_payload, {"input_tokens": 200, "output_tokens": 150})

            # 4. Run Extraction Pipeline (runs post-processing, validation, etc.)
            extraction = run_multi_stage_extraction(
                processed_pages,
                preprocessing_meta,
                profile=profile,
                route_decision=route_decision
            )

            # 5. Assertions
            self.assertEqual(extraction.status, "NEEDS_REVIEW")
            self.assertTrue(extraction.needs_review)
            self.assertEqual(extraction.traceability_status, "UNVERIFIED")
            self.assertIn("traceability_unverified", extraction.review_reasons)
            self.assertIn("critical_identifier_unverified", extraction.review_reasons)
            
            # Final user-facing invariant: all heat numbers are suppressed for review rows.
            for item in extraction.items:
                self.assertEqual(item.traceability_status, "UNVERIFIED")
                self.assertIsNone(item.heat_number)
                self.assertTrue(item.needs_review)
                if item.validation:
                    self.assertEqual(item.validation.outcome, "NEEDS_REVIEW")
                self.assertIn("heat_number", item.accepted_identifier_values)
                self.assertIsNone(item.accepted_identifier_values["heat_number"])
            self.assertIn("visual ambiguity detected in row", extraction.review_reasons)
            
            # Verify Identifier Guard Logging
            guard_meta = extraction.explanation.get("identifier_guard")
            self.assertIsNotNone(guard_meta)
            self.assertEqual(guard_meta["policy"], "strict_critical_identifier_acceptance_gate")
            self.assertEqual(guard_meta["quality_class"], "noisy_scan")
            
            # Check suppression events
            events = guard_meta.get("events", [])
            self.assertGreaterEqual(len(events), 3) # Rows 2, 3, 4 should have suppression events
            
            row2_event = next((e for e in events if e["row_index"] == 2), None)
            self.assertIsNotNone(row2_event)
            self.assertIn("heat_number", row2_event["suppressed_fields"])
            self.assertIn("item_id", row2_event["suppressed_fields"])
            self.assertTrue(row2_event["suppressed_identifiers"][0]["evidence_note"])
            self.assertIn("raw_candidate", row2_event["suppressed_identifiers"][0])
            
            # Mechanical values retained
            self.assertEqual(extraction.items[0].mechanical_properties.yield_strength_mpa, 264)
            self.assertEqual(extraction.items[0].mechanical_properties.tensile_strength_mpa, 418)
            self.assertEqual(extraction.items[1].mechanical_properties.yield_strength_mpa, 252)
            self.assertEqual(extraction.items[1].mechanical_properties.tensile_strength_mpa, 422)
            self.assertEqual(extraction.items[2].mechanical_properties.yield_strength_mpa, 258)
            self.assertEqual(extraction.items[3].mechanical_properties.tensile_strength_mpa, 424)
            self.assertEqual(extraction.items[4].mechanical_properties.elongation_percentage, 33)
            
            # Review reasons
            self.assertTrue(any("ambiguity" in r or "identifier" in r or "readability" in r for r in extraction.review_reasons))
            
            # Verification logic: Ensure no risky row is marked verified (if there was a per-row outcome)
            # In our system, extraction.outcome is document-level
            self.assertEqual(extraction.status, "NEEDS_REVIEW")

            # Remarks must not overstate identifier readability.
            self.assertIn("traceability-critical identifiers could not be verified", extraction.ai_analysis_remarks or "")

if __name__ == "__main__":
    unittest.main()
