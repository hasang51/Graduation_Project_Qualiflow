from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass
class PageVariantSet:
    original_width: int
    original_height: int
    variants: dict[str, np.ndarray]
    blur_score: float
    noise_estimate: float


@dataclass
class TableRegionDetection:
    table_found: bool
    bounding_box: tuple[int, int, int, int] | None
    crop_size: tuple[int, int] | None
    confidence: float
    line_mask: np.ndarray | None = None


def compute_blur_score(gray_image: np.ndarray) -> float:
    laplacian = cv2.Laplacian(gray_image, cv2.CV_64F)
    return float(laplacian.var())


def estimate_noise(gray_image: np.ndarray) -> float:
    # The residual between the source image and a lightly denoised copy is a practical
    # proxy for scanner noise without requiring extra dependencies.
    denoised = cv2.medianBlur(gray_image, 3)
    residual = cv2.absdiff(gray_image, denoised)
    return float(np.std(residual))


def denoise_grayscale(gray_image: np.ndarray) -> np.ndarray:
    return cv2.bilateralFilter(gray_image, d=7, sigmaColor=45, sigmaSpace=45)


def enhance_contrast(gray_image: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    return clahe.apply(gray_image)


def adaptive_threshold(gray_image: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(
        gray_image,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        35,
        11,
    )


def sharpen_with_unsharp_mask(gray_image: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray_image, (0, 0), sigmaX=1.2)
    return cv2.addWeighted(gray_image, 1.6, blurred, -0.6, 0)


def build_page_variants(gray_image: np.ndarray) -> PageVariantSet:
    height, width = gray_image.shape[:2]
    denoised = denoise_grayscale(gray_image)
    contrast = enhance_contrast(denoised)
    binary = adaptive_threshold(contrast)
    sharpened = sharpen_with_unsharp_mask(contrast)

    variants = {
        "full_gray": gray_image,
        "denoised": denoised,
        "contrast": contrast,
        "adaptive_binary": binary,
        "sharpened": sharpened,
    }
    return PageVariantSet(
        original_width=width,
        original_height=height,
        variants=variants,
        blur_score=compute_blur_score(gray_image),
        noise_estimate=estimate_noise(gray_image),
    )


def _enhance_table_lines(binary_image: np.ndarray) -> np.ndarray:
    height, width = binary_image.shape[:2]
    inverted = 255 - binary_image
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(24, width // 28), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(24, height // 28)))
    horizontal_lines = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, horizontal_kernel)
    vertical_lines = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, vertical_kernel)
    combined = cv2.addWeighted(horizontal_lines, 0.5, vertical_lines, 0.5, 0)
    combined = cv2.dilate(combined, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=1)
    return combined


def detect_table_region(binary_image: np.ndarray) -> TableRegionDetection:
    line_mask = _enhance_table_lines(binary_image)
    contours, _ = cv2.findContours(line_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return TableRegionDetection(False, None, None, 0.0, line_mask)

    height, width = binary_image.shape[:2]
    page_area = float(height * width)
    min_area = max(18000, int(page_area * 0.04))
    best_score = 0.0
    best_bbox: tuple[int, int, int, int] | None = None

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < min_area:
            continue
        ratio = w / max(h, 1)
        if not (0.5 <= ratio <= 8.0):
            continue

        roi_mask = line_mask[y : y + h, x : x + w]
        line_density = float(np.count_nonzero(roi_mask)) / float(max(area, 1))
        contour_area = float(cv2.contourArea(contour))
        rectangularity = contour_area / float(max(area, 1))
        area_score = min(1.0, area / (page_area * 0.45))
        score = (area_score * 0.45) + (line_density * 1.8 * 0.35) + (rectangularity * 0.20)

        if score > best_score:
            best_score = score
            best_bbox = (x, y, w, h)

    if best_bbox is None or best_score < 0.18:
        return TableRegionDetection(False, None, None, round(best_score, 3), line_mask)

    _, _, w, h = best_bbox
    return TableRegionDetection(True, best_bbox, (w, h), round(min(best_score, 1.0), 3), line_mask)


def _pad_bounding_box(
    bbox: tuple[int, int, int, int],
    image_shape: tuple[int, int],
    padding_ratio: float = 0.03,
) -> tuple[int, int, int, int]:
    x, y, w, h = bbox
    image_height, image_width = image_shape
    pad_x = max(12, int(w * padding_ratio))
    pad_y = max(12, int(h * padding_ratio))
    x0 = max(0, x - pad_x)
    y0 = max(0, y - pad_y)
    x1 = min(image_width, x + w + pad_x)
    y1 = min(image_height, y + h + pad_y)
    return (x0, y0, x1 - x0, y1 - y0)


def create_zoomed_table_variant(
    source_image: np.ndarray,
    detection: TableRegionDetection,
) -> tuple[np.ndarray | None, tuple[int, int, int, int] | None]:
    if not detection.table_found or detection.bounding_box is None:
        return None, None

    padded_bbox = _pad_bounding_box(detection.bounding_box, source_image.shape[:2])
    x, y, w, h = padded_bbox
    crop = source_image[y : y + h, x : x + w]
    if crop.size == 0:
        return None, None

    upscale_factor = 3 if max(w, h) < 900 else 2
    upscaled = cv2.resize(
        crop,
        (max(1, w * upscale_factor), max(1, h * upscale_factor)),
        interpolation=cv2.INTER_CUBIC,
    )
    return upscaled, padded_bbox


def save_debug_preview_images(
    artifact_dir: Path,
    page_number: int,
    variants: dict[str, np.ndarray],
) -> dict[str, str]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: dict[str, str] = {}
    for variant_name, variant_image in variants.items():
        target = artifact_dir / f"p{page_number:03d}_{variant_name}.png"
        cv2.imwrite(str(target), variant_image)
        saved_paths[variant_name] = str(target)
    return saved_paths


def variant_metadata(page_variant_set: PageVariantSet) -> dict[str, Any]:
    return {
        "original_width": page_variant_set.original_width,
        "original_height": page_variant_set.original_height,
        "variant_names": list(page_variant_set.variants.keys()),
        "blur_score": page_variant_set.blur_score,
        "noise_estimate": page_variant_set.noise_estimate,
    }
