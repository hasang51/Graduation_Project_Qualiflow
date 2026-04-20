from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BlurSeverity = Literal["low", "moderate", "high"]
NoiseSeverity = Literal["low", "moderate", "high"]
DocumentCondition = Literal["clean", "noisy", "blurry", "noisy_and_blurry"]

# Deterministic thresholds, aligned with existing confidence heuristics.
BLUR_HIGH_THRESHOLD = 80.0
BLUR_MODERATE_THRESHOLD = 150.0
NOISE_HIGH_THRESHOLD = 25.0
NOISE_MODERATE_THRESHOLD = 14.0

PRIMARY_FULL_PAGE_CANDIDATES = ("contrast", "sharpened", "denoised", "full_gray", "adaptive_binary")


@dataclass(frozen=True)
class ImageQualityAssessment:
    blur_score: float
    noise_estimate: float
    blur_severity: BlurSeverity
    noise_severity: NoiseSeverity
    detected_condition: DocumentCondition


@dataclass(frozen=True)
class VariantSelectionDecision:
    available_variants: list[str]
    selected_variants: list[str]
    primary_variant: str
    selection_reasoning: list[str]


def classify_blur_severity(blur_score: float) -> BlurSeverity:
    if blur_score < BLUR_HIGH_THRESHOLD:
        return "high"
    if blur_score < BLUR_MODERATE_THRESHOLD:
        return "moderate"
    return "low"


def classify_noise_severity(noise_estimate: float) -> NoiseSeverity:
    if noise_estimate >= NOISE_HIGH_THRESHOLD:
        return "high"
    if noise_estimate >= NOISE_MODERATE_THRESHOLD:
        return "moderate"
    return "low"


def detect_document_condition(*, blur_score: float, noise_estimate: float) -> ImageQualityAssessment:
    blur_severity = classify_blur_severity(blur_score)
    noise_severity = classify_noise_severity(noise_estimate)

    if noise_severity == "high" and blur_severity == "high":
        condition: DocumentCondition = "noisy_and_blurry"
    elif noise_severity == "high":
        condition = "noisy"
    elif blur_severity == "high":
        condition = "blurry"
    elif noise_severity == "moderate" and blur_severity == "moderate":
        condition = "noisy_and_blurry"
    elif noise_severity == "moderate":
        condition = "noisy"
    elif blur_severity == "moderate":
        condition = "blurry"
    else:
        condition = "clean"

    return ImageQualityAssessment(
        blur_score=blur_score,
        noise_estimate=noise_estimate,
        blur_severity=blur_severity,
        noise_severity=noise_severity,
        detected_condition=condition,
    )


def _append_if_available(target: list[str], available: set[str], *names: str) -> None:
    for name in names:
        if name in available and name not in target:
            target.append(name)


def select_preprocessing_variants(
    *,
    assessment: ImageQualityAssessment,
    available_variants: list[str],
    table_crop_available: bool,
) -> VariantSelectionDecision:
    available_set = set(available_variants)
    selected: list[str] = []
    reasoning: list[str] = []

    if assessment.detected_condition in ("noisy", "noisy_and_blurry"):
        _append_if_available(selected, available_set, "denoised", "adaptive_binary", "contrast")
        reasoning.append("noise-oriented strategy selected denoised + adaptive_binary + contrast")

    if assessment.detected_condition in ("blurry", "noisy_and_blurry"):
        _append_if_available(selected, available_set, "sharpened", "contrast")
        reasoning.append("blur-oriented strategy selected sharpened + contrast")

    if assessment.detected_condition == "clean":
        _append_if_available(selected, available_set, "full_gray", "contrast")
        reasoning.append("clean strategy selected full_gray + contrast")

    if table_crop_available:
        _append_if_available(selected, available_set, "table_crop")
        reasoning.append("table-focused variant prioritized because table crop is available")

    # Keep backward-compatible support variants to avoid brittle downstream behavior.
    _append_if_available(selected, available_set, "adaptive_binary", "full_gray")
    if not selected:
        _append_if_available(selected, available_set, "contrast", "full_gray", "denoised", "adaptive_binary", "sharpened")
        reasoning.append("fallback strategy selected because no preferred variant was available")

    primary_priority = PRIMARY_FULL_PAGE_CANDIDATES
    if assessment.detected_condition in ("blurry", "noisy_and_blurry"):
        primary_priority = ("sharpened", "contrast", "denoised", "full_gray", "adaptive_binary")
    elif assessment.detected_condition == "noisy":
        primary_priority = ("denoised", "adaptive_binary", "contrast", "full_gray", "sharpened")
    elif assessment.detected_condition == "clean":
        primary_priority = ("contrast", "full_gray", "denoised", "adaptive_binary", "sharpened")

    primary_variant = ""
    for candidate in primary_priority:
        if candidate in selected and candidate in available_set:
            primary_variant = candidate
            break
    if not primary_variant:
        primary_variant = selected[0]
        reasoning.append("primary full-page variant fallback applied")

    return VariantSelectionDecision(
        available_variants=sorted(available_set),
        selected_variants=selected,
        primary_variant=primary_variant,
        selection_reasoning=reasoning,
    )


# ---------------------------------------------------------------------------
# Route-driven variant selection
# ---------------------------------------------------------------------------
# Phase 2 introduces a document-level route that is chosen exactly once per
# document (see ``app.services.extraction_router``). The functions below map a
# route to a deterministic variant stack. They intentionally reuse the same
# underlying lists used by the per-page condition branches above, so no new
# variants are introduced at this layer.

_ROUTE_SYNTHETIC_CONDITION: dict[str, DocumentCondition] = {
    "native_multimodal": "clean",
    "rendered_multimodal": "clean",
    "preprocessed_multimodal": "noisy_and_blurry",
}


def variants_for_route(
    *,
    route: str,
    available_variants: list[str],
    table_crop_available: bool,
) -> VariantSelectionDecision:
    """Return a :class:`VariantSelectionDecision` for an explicit route.

    The route is the output of the extraction router and is the single source
    of truth for which variants flow to the multimodal model. No per-page
    condition override is applied.
    """

    synthetic_condition = _ROUTE_SYNTHETIC_CONDITION.get(route)
    if synthetic_condition is None:
        raise ValueError(f"Unknown route '{route}'")

    # Synthesise a minimal assessment so we can reuse ``select_preprocessing_variants``.
    if synthetic_condition == "clean":
        synthetic_assessment = ImageQualityAssessment(
            blur_score=300.0,
            noise_estimate=5.0,
            blur_severity="low",
            noise_severity="low",
            detected_condition="clean",
        )
    else:
        synthetic_assessment = ImageQualityAssessment(
            blur_score=40.0,
            noise_estimate=30.0,
            blur_severity="high",
            noise_severity="high",
            detected_condition="noisy_and_blurry",
        )

    decision = select_preprocessing_variants(
        assessment=synthetic_assessment,
        available_variants=available_variants,
        table_crop_available=table_crop_available,
    )

    # For ``rendered_multimodal`` we still want sharpened available as a
    # secondary variant even though the synthetic assessment is "clean".
    if route == "rendered_multimodal":
        available_set = set(available_variants)
        selected = list(decision.selected_variants)
        _append_if_available(selected, available_set, "sharpened")
        decision = VariantSelectionDecision(
            available_variants=decision.available_variants,
            selected_variants=selected,
            primary_variant=decision.primary_variant,
            selection_reasoning=[
                *decision.selection_reasoning,
                "route=rendered_multimodal appends sharpened as a fallback",
            ],
        )
    else:
        decision = VariantSelectionDecision(
            available_variants=decision.available_variants,
            selected_variants=decision.selected_variants,
            primary_variant=decision.primary_variant,
            selection_reasoning=[
                *decision.selection_reasoning,
                f"route={route}",
            ],
        )

    return decision

