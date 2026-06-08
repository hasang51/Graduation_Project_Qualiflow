from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from app.services.document_profiler import DocumentProfile
from app.services.extraction_pipeline import run_multi_stage_extraction


class Doc001RegressionTests(unittest.TestCase):
    def _get_mock_page(self):
        page_mock = MagicMock()
        page_mock.page_number = 1
        page_mock.table_crop_available = True
        return page_mock

    def _get_mock_profile(self):
        return DocumentProfile(
            document_id="doc001",
            filename="doc001.pdf",
            page_count=1,
            has_text_layer=True,
            text_density=0.8,
            blur_score=420.0,
            noise_score=2.0,
            table_presence_hint=True,
            quality_class="digital_clean",
            reasons=["text_layer_present"],
        )

    @patch("app.services.extraction_pipeline._run_metadata_extraction")
    @patch("app.services.extraction_pipeline._run_row_extraction")
    def test_colata_batch_identifier_remains_visible(self, mock_row, mock_meta):
        mock_meta.return_value = (
            {
                "supplier_name": "NOVOFIL S.p.A.",
                "document_type": "Mill Test Certificate",
                "product_category": "PIPE",
                "certificate_date": "08/07/2024",
                "batch_number": "410537",
                "traceability_identifier_label": "COLATA/BATCH n°",
                "traceability_identifier_type": "batch_number",
                "traceability_identifier_value": "410537",
                "confidence_score": 0.9,
                "field_confidence": {"batch_number": 0.96},
            },
            {"input_tokens": 100, "output_tokens": 40},
        )
        mock_row.return_value = (
            {
                "total_items_detected": 1,
                "items": [
                    {
                        "item_id": "1",
                        "heat_number": None,
                        "batch_number": "410537",
                        "grade": "NOVOFIL SG2/NOVOBRONZE SG2",
                        "weight_or_length": "1.080 Kg",
                        "traceability_identifier_label": "COLATA/BATCH n°",
                        "traceability_identifier_type": "batch_number",
                        "traceability_identifier_value": "410537",
                        "review_reasons": ["unresolved_spec"],
                        "field_confidence": {
                            "batch_number": 0.95,
                            "item_id": 0.95,
                            "yield_strength_mpa": 0.95,
                            "tensile_strength_mpa": 0.95,
                            "elongation_percentage": 0.95,
                        },
                        "row_confidence": 0.92,
                        "mechanical_properties": {
                            "yield_strength_mpa": 470,
                            "tensile_strength_mpa": 560,
                            "elongation_percentage": 26,
                        },
                    }
                ],
            },
            {"input_tokens": 250, "output_tokens": 120},
        )

        extraction = run_multi_stage_extraction(
            [self._get_mock_page()],
            {"pages": [{"table_detection": {"table_found": True}}]},
            profile=self._get_mock_profile(),
        )

        item = extraction.items[0]
        self.assertEqual(item.traceability_identifier_value, "410537")
        self.assertEqual(item.batch_number, "410537")
        self.assertNotIn("missing_critical_field:heat_number", extraction.review_reasons)
        self.assertNotIn(
            "traceability-critical identifiers could not be verified",
            (extraction.ai_analysis_remarks or "").lower(),
        )


if __name__ == "__main__":
    unittest.main()
