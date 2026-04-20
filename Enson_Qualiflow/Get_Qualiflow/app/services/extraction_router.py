"""Single-path extraction router.

Given a :class:`app.services.document_profiler.DocumentProfile`, picks exactly
one runtime route. The route is an input to the page-level preprocessing stage
(via :func:`app.services.preprocessing_strategy.variants_for_route`), which
selects a single variant stack — no parallel backends, no arbitrary fan-out.

Route semantics:
- ``native_multimodal`` — PDF has a usable text layer and reasonable image
  quality. We still rasterise (the multimodal model sees images), but skip the
  heavier denoise/sharpen variants.
- ``rendered_multimodal`` — plain scanned document, acceptable quality. Use
  contrast / full_gray plus an optional sharpened fallback.
- ``preprocessed_multimodal`` — degraded scan. Use the full denoise + adaptive
  binary + sharpen + (if present) table_crop stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.document_profiler import DocumentProfile, QualityClass

Route = Literal["native_multimodal", "rendered_multimodal", "preprocessed_multimodal"]

ROUTE_FOR_QUALITY_CLASS: dict[QualityClass, Route] = {
    "digital_clean": "native_multimodal",
    "scan_clean": "rendered_multimodal",
    "scan_degraded": "preprocessed_multimodal",
}

VALID_ROUTES: tuple[Route, ...] = (
    "native_multimodal",
    "rendered_multimodal",
    "preprocessed_multimodal",
)


@dataclass(frozen=True)
class RouteDecision:
    route: Route
    quality_class: QualityClass
    reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "route": self.route,
            "quality_class": self.quality_class,
            "reasons": list(self.reasons),
        }


def choose_route(profile: DocumentProfile) -> RouteDecision:
    """Return the single route that should handle this document."""

    route = ROUTE_FOR_QUALITY_CLASS.get(profile.quality_class, "rendered_multimodal")
    reasons = [f"quality_class={profile.quality_class}"]
    if profile.has_text_layer:
        reasons.append(f"has_text_layer(text_density={profile.text_density:.2f})")
    else:
        reasons.append("no_text_layer")
    if profile.quality_class == "scan_degraded":
        reasons.append(
            f"blur_score={profile.blur_score:.1f},noise_score={profile.noise_score:.1f}"
        )
    reasons.extend(profile.reasons)
    return RouteDecision(route=route, quality_class=profile.quality_class, reasons=reasons)


def force_route(route_name: str) -> RouteDecision:
    """Return a :class:`RouteDecision` for a manually forced route.

    Used by experiment modes B and C in the batch runner so the router can be
    bypassed without circumventing the rest of the pipeline.
    """

    if route_name not in VALID_ROUTES:
        raise ValueError(
            f"Unknown route '{route_name}'. Expected one of: {VALID_ROUTES}"
        )
    # Derive a synthetic quality class for logging.
    quality_class: QualityClass = {
        "native_multimodal": "digital_clean",
        "rendered_multimodal": "scan_clean",
        "preprocessed_multimodal": "scan_degraded",
    }[route_name]
    return RouteDecision(
        route=route_name,  # type: ignore[arg-type]
        quality_class=quality_class,
        reasons=[f"forced_route={route_name}"],
    )
