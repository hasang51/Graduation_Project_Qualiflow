from __future__ import annotations

import unittest

from app.services.document_profiler import (
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

    def test_scan_degraded_when_blur_is_severe(self):
        quality, _ = classify_profile(
            has_text_layer=False,
            blur_score=BLUR_DEGRADED_THRESHOLD - 10.0,
            noise_score=5.0,
            text_density=0.0,
        )
        self.assertEqual(quality, "scan_degraded")

    def test_scan_degraded_when_noise_is_severe(self):
        quality, _ = classify_profile(
            has_text_layer=False,
            blur_score=300.0,
            noise_score=NOISE_DEGRADED_THRESHOLD + 10.0,
            text_density=0.0,
        )
        self.assertEqual(quality, "scan_degraded")

    def test_scan_degraded_when_both_moderate(self):
        quality, _ = classify_profile(
            has_text_layer=False,
            blur_score=100.0,
            noise_score=18.0,
            text_density=0.0,
        )
        self.assertEqual(quality, "scan_degraded")

    def test_text_layer_but_degraded_image_still_degraded(self):
        quality, _ = classify_profile(
            has_text_layer=True,
            blur_score=40.0,
            noise_score=30.0,
            text_density=0.2,
        )
        self.assertEqual(quality, "scan_degraded")

    def test_text_density_floor_matters_for_digital_clean(self):
        quality, _ = classify_profile(
            has_text_layer=True,
            blur_score=300.0,
            noise_score=5.0,
            text_density=DIGITAL_TEXT_DENSITY_MIN / 2.0,
        )
        self.assertEqual(quality, "scan_clean")


if __name__ == "__main__":
    unittest.main()
