from __future__ import annotations

import unittest
from pathlib import Path

from app.services.document_profiler import (
    profile_document,
    BLUR_DEGRADED_THRESHOLD,
    DIGITAL_TEXT_DENSITY_MIN,
    NOISE_DEGRADED_THRESHOLD,
    classify_profile,
    _page_text_is_noisy_ocr,
)


class ClassifyProfileTests(unittest.TestCase):
    def test_digital_clean_when_text_layer_and_clean_image(self):
        quality, reasons = classify_profile(
            has_text_layer=True,
            blur_score=300.0,
            noise_score=5.0,
            text_density=0.35,
        )
        self.assertEqual(quality, "digital_clean")
        self.assertTrue(any("text_layer_present" in r for r in reasons))

    def test_scan_clean_when_no_text_but_clean_image(self):
        quality, reasons = classify_profile(
            has_text_layer=False,
            blur_score=300.0,
            noise_score=5.0,
            text_density=0.0,
        )
        self.assertEqual(quality, "scan_clean")
        self.assertIn("no_text_layer", reasons)

    def test_noisy_scan_when_blur_is_severe(self):
        quality, _ = classify_profile(
            has_text_layer=False,
            blur_score=BLUR_DEGRADED_THRESHOLD - 10.0,
            noise_score=5.0,
            text_density=0.0,
        )
        self.assertEqual(quality, "noisy_scan")

    def test_noisy_scan_when_noise_is_severe(self):
        quality, _ = classify_profile(
            has_text_layer=False,
            blur_score=300.0,
            noise_score=NOISE_DEGRADED_THRESHOLD + 10.0,
            text_density=0.0,
        )
        self.assertIn(quality, {"noisy_scan", "severe_scan"})

    def test_noisy_scan_when_both_moderate(self):
        quality, _ = classify_profile(
            has_text_layer=False,
            blur_score=100.0,
            noise_score=18.0,
            text_density=0.0,
        )
        self.assertEqual(quality, "noisy_scan")

    def test_text_layer_but_degraded_image_still_noisy(self):
        quality, _ = classify_profile(
            has_text_layer=True,
            blur_score=40.0,
            noise_score=30.0,
            text_density=0.2,
        )
        self.assertIn(quality, {"noisy_scan", "severe_scan"})

    def test_severe_scan_when_blur_and_noise_extreme(self):
        quality, reasons = classify_profile(
            has_text_layer=False,
            blur_score=30.0,
            noise_score=45.0,
            text_density=0.0,
        )
        self.assertEqual(quality, "severe_scan")
        self.assertTrue(any("severe" in reason for reason in reasons))

    def test_text_density_floor_matters_for_digital_clean(self):
        quality, _ = classify_profile(
            has_text_layer=True,
            blur_score=300.0,
            noise_score=5.0,
            text_density=DIGITAL_TEXT_DENSITY_MIN / 2.0,
        )
        self.assertEqual(quality, "scan_clean")

    def test_replacement_char_check_does_not_flag_clean_text(self):
        clean_text = (
            "Mill Test Certificate EN 10204 3.1 Supplier: Example Steel Co. "
            "Heat number 12345678 Grade S355 Yield 355 MPa Tensile 510 MPa."
        )
        self.assertGreater(len(clean_text), 40)
        # Python's str.count("") is len(text)+1 and must not be used for OCR checks.
        self.assertGreater(clean_text.count(""), len(clean_text))
        self.assertFalse(_page_text_is_noisy_ocr(clean_text))

    def test_clean_text_layer_with_small_images_is_digital_clean(self):
        quality, reasons = classify_profile(
            has_text_layer=True,
            blur_score=300.0,
            noise_score=5.0,
            text_density=0.35,
            is_noisy_ocr=False,
            has_full_page_raster_image=False,
        )
        self.assertEqual(quality, "digital_clean")
        self.assertNotIn("full_page_raster_image", reasons)
        self.assertNotIn("ocr_text_layer_corrupted", reasons)

    def test_corrupted_ocr_and_large_raster_remains_noisy_scan(self):
        quality, reasons = classify_profile(
            has_text_layer=True,
            blur_score=300.0,
            noise_score=5.0,
            text_density=0.35,
            is_noisy_ocr=True,
            has_full_page_raster_image=True,
        )
        self.assertEqual(quality, "noisy_scan")
        self.assertIn("ocr_text_layer_corrupted", reasons)
        self.assertIn("full_page_raster_image", reasons)
        self.assertIn("low_identifier_legibility", reasons)

    def test_doc001_profiles_as_noisy_scan_not_severe_scan(self):
        pdf_path = Path("data/eval_docs/doc001.pdf")
        if not pdf_path.exists():
            self.skipTest("doc001.pdf not found")

        profile = profile_document(pdf_path)

        self.assertNotEqual(profile.quality_class, "severe_scan")
        self.assertEqual(profile.quality_class, "noisy_scan")
        self.assertGreater(profile.blur_score, 25.0)


if __name__ == "__main__":
    unittest.main()
