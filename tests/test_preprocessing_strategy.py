from __future__ import annotations

import unittest

from app.services.preprocessing_strategy import (
    classify_blur_severity,
    classify_noise_severity,
    detect_document_condition,
    select_preprocessing_variants,
)


ALL_VARIANTS = [
    "full_gray",
    "denoised",
    "contrast",
    "adaptive_binary",
    "sharpened",
]


class ClassificationTests(unittest.TestCase):
    def test_blur_severity_buckets(self):
        self.assertEqual(classify_blur_severity(20.0), "high")
        self.assertEqual(classify_blur_severity(100.0), "moderate")
        self.assertEqual(classify_blur_severity(200.0), "low")

    def test_noise_severity_buckets(self):
        self.assertEqual(classify_noise_severity(5.0), "low")
        self.assertEqual(classify_noise_severity(18.0), "moderate")
        self.assertEqual(classify_noise_severity(30.0), "high")


class DetectDocumentConditionTests(unittest.TestCase):
    def test_clean_when_both_low(self):
        result = detect_document_condition(blur_score=300.0, noise_estimate=5.0)
        self.assertEqual(result.detected_condition, "clean")

    def test_noisy_when_noise_high_blur_low(self):
        result = detect_document_condition(blur_score=300.0, noise_estimate=30.0)
        self.assertEqual(result.detected_condition, "noisy")

    def test_blurry_when_blur_high_noise_low(self):
        result = detect_document_condition(blur_score=20.0, noise_estimate=5.0)
        self.assertEqual(result.detected_condition, "blurry")

    def test_noisy_and_blurry_when_both_high(self):
        result = detect_document_condition(blur_score=20.0, noise_estimate=30.0)
        self.assertEqual(result.detected_condition, "noisy_and_blurry")

    def test_both_moderate_counts_as_noisy_and_blurry(self):
        result = detect_document_condition(blur_score=100.0, noise_estimate=18.0)
        self.assertEqual(result.detected_condition, "noisy_and_blurry")


class SelectPreprocessingVariantsTests(unittest.TestCase):
    def test_clean_page_prefers_full_gray_and_contrast(self):
        assessment = detect_document_condition(blur_score=300.0, noise_estimate=5.0)
        decision = select_preprocessing_variants(
            assessment=assessment,
            available_variants=ALL_VARIANTS,
            table_crop_available=False,
        )
        self.assertIn("full_gray", decision.selected_variants)
        self.assertIn("contrast", decision.selected_variants)
        self.assertEqual(decision.primary_variant, "contrast")

    def test_noisy_page_selects_denoising_stack(self):
        assessment = detect_document_condition(blur_score=300.0, noise_estimate=30.0)
        decision = select_preprocessing_variants(
            assessment=assessment,
            available_variants=ALL_VARIANTS,
            table_crop_available=False,
        )
        for expected in ("denoised", "adaptive_binary", "contrast"):
            self.assertIn(expected, decision.selected_variants)
        self.assertEqual(decision.primary_variant, "denoised")

    def test_blurry_page_selects_sharpening_stack(self):
        assessment = detect_document_condition(blur_score=20.0, noise_estimate=5.0)
        decision = select_preprocessing_variants(
            assessment=assessment,
            available_variants=ALL_VARIANTS,
            table_crop_available=False,
        )
        for expected in ("sharpened", "contrast"):
            self.assertIn(expected, decision.selected_variants)
        self.assertEqual(decision.primary_variant, "sharpened")

    def test_table_crop_is_prioritized_when_available_without_duplication(self):
        assessment = detect_document_condition(blur_score=300.0, noise_estimate=5.0)
        available = [*ALL_VARIANTS, "table_crop"]
        decision = select_preprocessing_variants(
            assessment=assessment,
            available_variants=available,
            table_crop_available=True,
        )
        self.assertIn("table_crop", decision.selected_variants)
        # Regression guard: the old aliasing bug appended both table_crop and
        # upscaled_table_crop for the same underlying array.
        self.assertNotIn("upscaled_table_crop", decision.selected_variants)
        self.assertEqual(
            decision.selected_variants.count("table_crop"),
            1,
            "table_crop must be emitted exactly once",
        )

    def test_primary_variant_fallback_when_priorities_not_present(self):
        assessment = detect_document_condition(blur_score=20.0, noise_estimate=5.0)
        decision = select_preprocessing_variants(
            assessment=assessment,
            # No sharpened/contrast available; forces fallback branch.
            available_variants=["full_gray"],
            table_crop_available=False,
        )
        self.assertEqual(decision.selected_variants, ["full_gray"])
        self.assertEqual(decision.primary_variant, "full_gray")


if __name__ == "__main__":
    unittest.main()
