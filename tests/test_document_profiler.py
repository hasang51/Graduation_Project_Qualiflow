from __future__ import annotations

import unittest
from pathlib import Path

from app.services.document_profiler import (
    profile_document,
    BLUR_DEGRADED_THRESHOLD,
    DIGITAL_TEXT_DENSITY_MIN,
    NOISE_DEGRADED_THRESHOLD,
    classify_profile,
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
