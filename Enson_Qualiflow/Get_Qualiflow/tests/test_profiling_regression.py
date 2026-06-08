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
        self.assertEqual(profile.metrics_summary["ocr_likelihood"], "high")

if __name__ == "__main__":
    unittest.main()
