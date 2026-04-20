"""Explainable 4-path extraction router.

The router emits an explicit decision table result:

- Path A: digital PDF -> native multimodal
- Path B: clean scan -> rendered multimodal
- Path C: degraded scan -> preprocessed multimodal
- Path D: severe scan -> conservative preprocessed route with review-first bias
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.document_profiler import DocumentProfile, QualityClass

Route = Literal[
    "path_a_digital_pdf",
    "path_b_clean_scan",
    "path_c_degraded_scan",
    "path_d_severe_scan",
]
RuntimeRoute = Literal["native_multimodal", "rendered_multimodal", "preprocessed_multimodal"]

ROUTE_FOR_QUALITY_CLASS: dict[QualityClass, Route] = {
    "digital_clean": "path_a_digital_pdf",
    "scan_clean": "path_b_clean_scan",
    "scan_degraded": "path_c_degraded_scan",
    "severe_scan": "path_d_severe_scan",
}

RUNTIME_ROUTE_FOR_ROUTE: dict[Route, RuntimeRoute] = {
    "path_a_digital_pdf": "native_multimodal",
    "path_b_clean_scan": "rendered_multimodal",
    "path_c_degraded_scan": "preprocessed_multimodal",
    "path_d_severe_scan": "preprocessed_multimodal",
}

VALID_ROUTES: tuple[Route, ...] = (
    "path_a_digital_pdf",
    "path_b_clean_scan",
    "path_c_degraded_scan",
    "path_d_severe_scan",
)


@dataclass(frozen=True)
class RouteDecision:
    selected_route: Route
    runtime_route: RuntimeRoute
    quality_class: QualityClass
    reason_codes: list[str]
    triggering_features: dict[str, float | bool | int]
    expected_strategy: str
    review_first_bias: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "selected_route": self.selected_route,
            "runtime_route": self.runtime_route,
            "route": self.runtime_route,
            "quality_class": self.quality_class,
            "reason_codes": list(self.reason_codes),
            "reasons": list(self.reason_codes),
            "triggering_features": dict(self.triggering_features),
            "expected_strategy": self.expected_strategy,
            "review_first_bias": self.review_first_bias,
        }


def choose_route(profile: DocumentProfile) -> RouteDecision:
    """Return the single route that should handle this document."""

    route = ROUTE_FOR_QUALITY_CLASS.get(profile.quality_class, "path_b_clean_scan")
    runtime_route = RUNTIME_ROUTE_FOR_ROUTE[route]
    reasons = [f"quality_class:{profile.quality_class}"]
    if profile.has_text_layer:
        reasons.append("text_layer_present")
    else:
        reasons.append("no_text_layer")
    reasons.extend(profile.reasons)
    strategy = {
        "path_a_digital_pdf": "digital images, minimal preprocessing",
        "path_b_clean_scan": "clean raster rendering with light variant fallback",
        "path_c_degraded_scan": "denoise + adaptive binary + sharpen stack",
        "path_d_severe_scan": "minimal attempt, then review-first gate",
    }[route]
    return RouteDecision(
        selected_route=route,
        runtime_route=runtime_route,
        quality_class=profile.quality_class,
        reason_codes=reasons,
        triggering_features={
            "has_text_layer": profile.has_text_layer,
            "text_density": profile.text_density,
            "blur_score": profile.blur_score,
            "noise_score": profile.noise_score,
            "page_count": profile.page_count,
            "table_presence_hint": profile.table_presence_hint,
        },
        expected_strategy=strategy,
        review_first_bias=route == "path_d_severe_scan",
    )


def force_route(route_name: str) -> RouteDecision:
    """Return a :class:`RouteDecision` for a manually forced route.

    Used by experiment modes B and C in the batch runner so the router can be
    bypassed without circumventing the rest of the pipeline.
    """

    legacy_map: dict[str, Route] = {
        "native_multimodal": "path_a_digital_pdf",
        "rendered_multimodal": "path_b_clean_scan",
        "preprocessed_multimodal": "path_c_degraded_scan",
    }
    coerced_route = legacy_map.get(route_name, route_name)
    if coerced_route not in VALID_ROUTES:
        raise ValueError(
            f"Unknown route '{route_name}'. Expected one of: {VALID_ROUTES}"
        )
    route = coerced_route  # type: ignore[assignment]
    quality_class: QualityClass = {
        "path_a_digital_pdf": "digital_clean",
        "path_b_clean_scan": "scan_clean",
        "path_c_degraded_scan": "scan_degraded",
        "path_d_severe_scan": "severe_scan",
    }[route]
    return RouteDecision(
        selected_route=route,
        runtime_route=RUNTIME_ROUTE_FOR_ROUTE[route],
        quality_class=quality_class,
        reason_codes=[f"forced_route:{route_name}"],
        triggering_features={},
        expected_strategy="manual route override",
        review_first_bias=route == "path_d_severe_scan",
    )
