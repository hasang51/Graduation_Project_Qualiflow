from __future__ import annotations

import unittest

from app.services.document_profiler import DocumentProfile
from app.services.extraction_router import (
    VALID_ROUTES,
    choose_route,
    force_route,
)


def _profile(
    *,
    quality_class: str,
    has_text_layer: bool = False,
    blur_score: float = 200.0,
    noise_score: float = 5.0,
    text_density: float = 0.0,
) -> DocumentProfile:
    return DocumentProfile(
        document_id="abc",
        filename="x.pdf",
        page_count=1,
        has_text_layer=has_text_layer,
        text_density=text_density,
        blur_score=blur_score,
        noise_score=noise_score,
        table_presence_hint=False,
        quality_class=quality_class,  # type: ignore[arg-type]
        reasons=["synthetic"],
    )


class ChooseRouteTests(unittest.TestCase):
    def test_digital_clean_selects_native_multimodal(self):
        decision = choose_route(_profile(quality_class="digital_clean", has_text_layer=True, text_density=0.5))
        self.assertEqual(decision.selected_route, "path_a_digital_pdf")
        self.assertEqual(decision.runtime_route, "native_multimodal")
        self.assertEqual(decision.quality_class, "digital_clean")

    def test_scan_clean_selects_rendered_multimodal(self):
        decision = choose_route(_profile(quality_class="scan_clean"))
        self.assertEqual(decision.selected_route, "path_b_clean_scan")
        self.assertEqual(decision.runtime_route, "rendered_multimodal")

    def test_noisy_scan_selects_preprocessed_multimodal(self):
        decision = choose_route(
            _profile(quality_class="noisy_scan", blur_score=50.0, noise_score=30.0)
        )
        self.assertEqual(decision.selected_route, "path_c_noisy_scan")
        self.assertEqual(decision.runtime_route, "preprocessed_multimodal")

    def test_severe_scan_selects_review_first_path(self):
        decision = choose_route(_profile(quality_class="severe_scan", blur_score=20.0, noise_score=45.0))
        self.assertEqual(decision.selected_route, "path_d_severe_scan")
        self.assertTrue(decision.review_first_bias)

    def test_route_is_exactly_one_of_valid_routes(self):
        for quality in ("digital_clean", "scan_clean", "noisy_scan", "severe_scan"):
            decision = choose_route(_profile(quality_class=quality))
            self.assertIn(decision.selected_route, VALID_ROUTES)


class ForceRouteTests(unittest.TestCase):
    def test_force_route_accepts_valid(self):
        for route in VALID_ROUTES:
            decision = force_route(route)
            self.assertEqual(decision.selected_route, route)

    def test_force_route_rejects_unknown(self):
        with self.assertRaises(ValueError):
            force_route("invented_route")


if __name__ == "__main__":
    unittest.main()
