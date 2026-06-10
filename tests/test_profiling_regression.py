from __future__ import annotations

import unittest
from pathlib import Path
from app.services.document_profiler import profile_document

class ProfilingRegressionTests(unittest.TestCase):
    def test_doc008_not_digital_clean(self):
        """doc008 is a scan with noisy OCR and should be noisy_scan, not digital_clean."""
        pdf_path = Path("data/eval_docs/doc008.pdf")
        if not pdf_path.exists():
            self.skipTest("doc008.pdf not found")
            
        profile = profile_document(pdf_path)
        
        # Core requirement: must not be digital_clean
        self.assertNotEqual(profile.quality_class, "digital_clean")
        self.assertEqual(profile.quality_class, "noisy_scan")
        
        # Required reasons presence
        self.assertIn("ocr_text_layer_corrupted", profile.reasons)
        self.assertIn("full_page_raster_image", profile.reasons)
        self.assertIn("low_identifier_legibility", profile.reasons)
        
        # Verify it has images detected
        self.assertTrue(profile.metrics_summary["has_extractable_text"])
        self.assertTrue(profile.metrics_summary["has_full_page_raster_image"])
        self.assertEqual(profile.metrics_summary["ocr_likelihood"], "high")

    def test_doc016_clean_text_layer_with_logos_not_noisy_scan(self):
        """doc016 is a digital PDF with logos; it must not be misclassified as noisy_scan."""
        pdf_path = Path("data/eval_docs/doc016.pdf")
        if not pdf_path.exists():
            self.skipTest("doc016.pdf not found")

        profile = profile_document(pdf_path)

        self.assertNotEqual(profile.quality_class, "noisy_scan")
        self.assertNotIn("ocr_text_layer_corrupted", profile.reasons)
        self.assertNotIn("full_page_raster_image", profile.reasons)
        self.assertFalse(profile.metrics_summary["has_full_page_raster_image"])
        self.assertTrue(profile.metrics_summary["has_embedded_images"])

if __name__ == "__main__":
    unittest.main()
