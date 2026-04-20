from __future__ import annotations

import base64
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from pdf2image import convert_from_path
from PIL import Image

from app.config import settings
from app.services.image_preprocessing import (
    build_page_variants,
    create_zoomed_table_variant,
    detect_table_region,
    save_debug_preview_images,
    variant_metadata,
)
from app.services.preprocessing_strategy import (
    detect_document_condition,
    select_preprocessing_variants,
    variants_for_route,
)
from app.services.table_parser import parse_table_structure


@dataclass
class EncodedVariant:
    data: str
    media_type: str
    width: int
    height: int
    byte_size: int


@dataclass
class ProcessedPage:
    page_number: int
    variants: dict[str, EncodedVariant]
    table_crop_bbox: tuple[int, int, int, int] | None
    table_crop_available: bool
    full_page_variant_name: str
    selected_variants: list[str]
    primary_variant: str
    detected_condition: str


def _downscale_to_max_edge(arr: np.ndarray, max_edge: int) -> np.ndarray:
    height, width = arr.shape[:2]
    current_max = max(height, width)
    if current_max <= max_edge:
        return arr
    scale = max_edge / current_max
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))
    return cv2.resize(arr, (new_width, new_height), interpolation=cv2.INTER_AREA)


def _encode_variant_for_llm(arr: np.ndarray, prefer_png: bool = False) -> EncodedVariant:
    resized = _downscale_to_max_edge(arr, settings.llm_image_max_edge)
    height, width = resized.shape[:2]

    if prefer_png:
        ok, buf = cv2.imencode(".png", resized, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        if not ok:
            raise ValueError("Failed to encode PNG image.")
        raw = buf.tobytes()
        if len(raw) <= settings.llm_image_target_bytes:
            return EncodedVariant(
                data=base64.b64encode(raw).decode("utf-8"),
                media_type="image/png",
                width=width,
                height=height,
                byte_size=len(raw),
            )

    quality = settings.llm_jpeg_quality
    current = resized
    while True:
        ok, buf = cv2.imencode(".jpg", current, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise ValueError("Failed to encode JPEG image.")
        raw = buf.tobytes()
        if len(raw) <= settings.llm_image_target_bytes:
            final_height, final_width = current.shape[:2]
            return EncodedVariant(
                data=base64.b64encode(raw).decode("utf-8"),
                media_type="image/jpeg",
                width=final_width,
                height=final_height,
                byte_size=len(raw),
            )
        if quality > 55:
            quality -= 8
            continue
        next_max_edge = max(settings.llm_image_min_edge, int(max(current.shape[:2]) * 0.82))
        if next_max_edge >= max(current.shape[:2]):
            next_max_edge = max(settings.llm_image_min_edge, max(current.shape[:2]) - 120)
        if next_max_edge < settings.llm_image_min_edge or next_max_edge == max(current.shape[:2]):
            final_height, final_width = current.shape[:2]
            return EncodedVariant(
                data=base64.b64encode(raw).decode("utf-8"),
                media_type="image/jpeg",
                width=final_width,
                height=final_height,
                byte_size=len(raw),
            )
        current = _downscale_to_max_edge(current, next_max_edge)
        quality = settings.llm_jpeg_quality


def preprocess_pdf(
    pdf_path: str,
    artifact_dir: Path,
    route: str | None = None,
    max_pages: int | None = None,
) -> tuple[list[ProcessedPage], dict[str, Any]]:
    poppler_kwargs = {}
    if sys.platform == "win32":
        poppler_kwargs["poppler_path"] = settings.poppler_path

    # ``max_pages`` is opt-in. The runtime route keeps the default (None) so
    # behaviour there is unchanged. The batch runner passes
    # ``settings.max_pages_for_llm`` to avoid rasterising pages that the LLM
    # would never see (Stage A / Stage B already truncate at that count).
    convert_kwargs = dict(poppler_kwargs)
    if max_pages is not None and max_pages > 0:
        convert_kwargs["first_page"] = 1
        convert_kwargs["last_page"] = max_pages

    pages = convert_from_path(pdf_path, dpi=settings.pdf_dpi, fmt="png", grayscale=True, **convert_kwargs)
    processed: list[ProcessedPage] = []
    meta_pages: list[dict[str, Any]] = []
    condition_counts: dict[str, int] = {"clean": 0, "noisy": 0, "blurry": 0, "noisy_and_blurry": 0}

    for idx, page in enumerate(pages, start=1):
        gray_pil: Image.Image = page.convert("L")
        gray = np.array(gray_pil)
        page_variants = build_page_variants(gray)
        variants_np = dict(page_variants.variants)
        table_detection = detect_table_region(variants_np["adaptive_binary"])
        padded_table_bbox = None

        if table_detection.line_mask is not None:
            variants_np["table_line_mask"] = table_detection.line_mask

        table_zoom, padded_table_bbox = create_zoomed_table_variant(variants_np["contrast"], table_detection)
        if table_zoom is not None:
            variants_np["table_crop"] = table_zoom

        quality_assessment = detect_document_condition(
            blur_score=page_variants.blur_score,
            noise_estimate=page_variants.noise_estimate,
        )
        if route is not None:
            selection = variants_for_route(
                route=route,
                available_variants=list(variants_np.keys()),
                table_crop_available="table_crop" in variants_np,
            )
        else:
            selection = select_preprocessing_variants(
                assessment=quality_assessment,
                available_variants=list(variants_np.keys()),
                table_crop_available="table_crop" in variants_np,
            )
        condition_counts[quality_assessment.detected_condition] += 1
        table_parse = parse_table_structure(
            page_number=idx,
            variants_np=variants_np,
            table_detection=table_detection,
            artifact_dir=artifact_dir,
        )

        variants_encoded = {
            name: _encode_variant_for_llm(arr, prefer_png=name == "adaptive_binary")
            for name, arr in variants_np.items()
        }
        saved_variant_paths = save_debug_preview_images(artifact_dir, idx, variants_np)

        processed.append(
            ProcessedPage(
                page_number=idx,
                variants=variants_encoded,
                table_crop_bbox=padded_table_bbox,
                table_crop_available="table_crop" in variants_encoded,
                full_page_variant_name=selection.primary_variant,
                selected_variants=selection.selected_variants,
                primary_variant=selection.primary_variant,
                detected_condition=quality_assessment.detected_condition,
            )
        )
        meta_pages.append(
            {
                "page": idx,
                **variant_metadata(page_variants),
                "variants": {
                    name: {
                        "media_type": variant.media_type,
                        "width": variant.width,
                        "height": variant.height,
                        "byte_size": variant.byte_size,
                        "debug_path": saved_variant_paths.get(name),
                    }
                    for name, variant in variants_encoded.items()
                },
                "table_detection": {
                    "table_found": table_detection.table_found,
                    "bounding_box": table_detection.bounding_box,
                    "crop_size": table_detection.crop_size,
                    "confidence": table_detection.confidence,
                    "padded_bounding_box": padded_table_bbox,
                },
                "quality_assessment": {
                    "blur_score": quality_assessment.blur_score,
                    "noise_estimate": quality_assessment.noise_estimate,
                    "blur_severity": quality_assessment.blur_severity,
                    "noise_severity": quality_assessment.noise_severity,
                    "detected_condition": quality_assessment.detected_condition,
                },
                "variant_selection": {
                    "available_variants": selection.available_variants,
                    "selected_variants": selection.selected_variants,
                    "primary_variant": selection.primary_variant,
                    "selection_reasoning": selection.selection_reasoning,
                },
                "table_parsing": table_parse.to_dict(),
            }
        )

    dominant_condition = max(condition_counts.items(), key=lambda row: row[1])[0] if processed else "clean"
    meta = {
        "page_count": len(processed),
        "pages": meta_pages,
        "adaptive_preprocessing_summary": {
            "condition_counts": condition_counts,
            "dominant_condition": dominant_condition,
            "strategy_version": "v1",
        },
    }
    if route is not None:
        meta["route_used"] = route
    return processed, meta
