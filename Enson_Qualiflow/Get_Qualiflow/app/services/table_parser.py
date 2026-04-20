from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.services.image_preprocessing import TableRegionDetection

TARGET_CANONICAL_COLUMNS = [
    "item_id",
    "heat_number",
    "grade",
    "weight_or_length",
    "yield_strength_mpa",
    "tensile_strength_mpa",
    "elongation_percentage",
]


@dataclass(frozen=True)
class BBox:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    def to_dict(self) -> dict[str, int]:
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}


@dataclass(frozen=True)
class HeaderDetectionResult:
    header_found: bool
    header_bbox: BBox | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "header_found": self.header_found,
            "header_bbox": self.header_bbox.to_dict() if self.header_bbox else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ColumnBand:
    column_index: int
    x_min: int
    x_max: int
    canonical_field: str | None
    mapping_confidence: float
    mapping_note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "column_index": self.column_index,
            "x_min": self.x_min,
            "x_max": self.x_max,
            "canonical_field": self.canonical_field,
            "mapping_confidence": self.mapping_confidence,
            "mapping_note": self.mapping_note,
        }


@dataclass(frozen=True)
class RowSegment:
    row_index: int
    bbox: BBox
    is_header: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_index": self.row_index,
            "bbox": self.bbox.to_dict(),
            "is_header": self.is_header,
        }


@dataclass(frozen=True)
class CellCrop:
    row_index: int
    column_index: int
    canonical_field: str | None
    bbox: BBox
    image_path: str
    page_number: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_index": self.row_index,
            "column_index": self.column_index,
            "canonical_field": self.canonical_field,
            "bbox": self.bbox.to_dict(),
            "image_path": self.image_path,
            "page_number": self.page_number,
        }


@dataclass
class TableParseResult:
    page_number: int
    source_variant: str
    table_found: bool
    table_bbox: BBox | None
    table_confidence: float
    header_result: HeaderDetectionResult
    column_bands: list[ColumnBand] = field(default_factory=list)
    row_segments: list[RowSegment] = field(default_factory=list)
    cell_crops: list[CellCrop] = field(default_factory=list)
    semantic_mapping_notes: list[str] = field(default_factory=list)
    quality_indicators: dict[str, Any] = field(default_factory=dict)
    debug_overlay_path: str | None = None
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "source_variant": self.source_variant,
            "table_found": self.table_found,
            "table_bbox": self.table_bbox.to_dict() if self.table_bbox else None,
            "table_confidence": self.table_confidence,
            "header_result": self.header_result.to_dict(),
            "column_bands": [column.to_dict() for column in self.column_bands],
            "row_segments": [row.to_dict() for row in self.row_segments],
            "cell_crops": [cell.to_dict() for cell in self.cell_crops],
            "semantic_mapping_notes": self.semantic_mapping_notes,
            "quality_indicators": self.quality_indicators,
            "debug_overlay_path": self.debug_overlay_path,
            "failure_reason": self.failure_reason,
        }


def _group_positions(positions: list[int], gap: int = 8) -> list[int]:
    if not positions:
        return []
    grouped = [[positions[0]]]
    for value in positions[1:]:
        if abs(value - grouped[-1][-1]) <= gap:
            grouped[-1].append(value)
        else:
            grouped.append([value])
    return [int(sum(group) / len(group)) for group in grouped]


def _line_positions(binary_crop: np.ndarray, axis: str) -> list[int]:
    inv = 255 - binary_crop
    height, width = binary_crop.shape[:2]
    if axis == "vertical":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(22, height // 25)))
        lines = cv2.morphologyEx(inv, cv2.MORPH_OPEN, kernel)
        counts = np.count_nonzero(lines, axis=0)
        threshold = max(10, int(0.55 * height))
    else:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(22, width // 25), 1))
        lines = cv2.morphologyEx(inv, cv2.MORPH_OPEN, kernel)
        counts = np.count_nonzero(lines, axis=1)
        threshold = max(10, int(0.55 * width))
    positions = [idx for idx, value in enumerate(counts.tolist()) if value >= threshold]
    return _group_positions(positions)


def _fallback_table_bbox(binary_image: np.ndarray) -> BBox | None:
    inv = 255 - binary_image
    contours, _ = cv2.findContours(inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    h, w = binary_image.shape[:2]
    page_area = h * w
    best = None
    best_area = 0
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        area = bw * bh
        if area > best_area and area >= int(0.2 * page_area):
            best = BBox(x, y, x + bw, y + bh)
            best_area = area
    return best


def _resolve_table_bbox(table_detection: TableRegionDetection, binary_image: np.ndarray) -> tuple[BBox | None, float]:
    if table_detection.table_found and table_detection.bounding_box:
        x, y, w, h = table_detection.bounding_box
        return BBox(x, y, x + w, y + h), float(table_detection.confidence)
    fallback = _fallback_table_bbox(binary_image)
    return fallback, 0.15 if fallback else 0.0


def _detect_header(table_binary: np.ndarray, table_bbox: BBox, horizontal_lines: list[int]) -> HeaderDetectionResult:
    if len(horizontal_lines) >= 2:
        y1 = horizontal_lines[0]
        y2 = horizontal_lines[1]
        if y2 > y1 + 4:
            return HeaderDetectionResult(
                header_found=True,
                header_bbox=BBox(table_bbox.x1, table_bbox.y1 + y1, table_bbox.x2, table_bbox.y1 + y2),
                reason="header inferred from first horizontal grid band",
            )
    height = table_binary.shape[0]
    fallback_height = max(18, int(height * 0.12))
    return HeaderDetectionResult(
        header_found=False,
        header_bbox=BBox(table_bbox.x1, table_bbox.y1, table_bbox.x2, table_bbox.y1 + fallback_height),
        reason="header unresolved; using top table band fallback",
    )


def _derive_columns(table_bbox: BBox, vertical_lines: list[int]) -> tuple[list[ColumnBand], list[str]]:
    notes: list[str] = []
    boundaries = [0, *vertical_lines, table_bbox.width]
    boundaries = sorted(set(boundaries))
    if len(boundaries) < 3:
        notes.append("insufficient vertical separators; equal-width fallback used")
        step = max(1, table_bbox.width // len(TARGET_CANONICAL_COLUMNS))
        boundaries = [0]
        for index in range(1, len(TARGET_CANONICAL_COLUMNS)):
            boundaries.append(min(table_bbox.width, index * step))
        boundaries.append(table_bbox.width)

    bands: list[ColumnBand] = []
    intervals = list(zip(boundaries[:-1], boundaries[1:]))
    usable = [(x1, x2) for x1, x2 in intervals if x2 - x1 >= 8]
    for idx, (x1, x2) in enumerate(usable):
        canonical = TARGET_CANONICAL_COLUMNS[idx] if idx < len(TARGET_CANONICAL_COLUMNS) else None
        confidence = 0.9 if canonical is not None else 0.5
        note = "positional mapping against canonical target set" if canonical else "no canonical mapping slot"
        bands.append(
            ColumnBand(
                column_index=idx,
                x_min=table_bbox.x1 + x1,
                x_max=table_bbox.x1 + x2,
                canonical_field=canonical,
                mapping_confidence=confidence,
                mapping_note=note,
            )
        )
    if len(bands) < len(TARGET_CANONICAL_COLUMNS):
        notes.append("column count lower than expected canonical target columns")
    return bands, notes


def _derive_rows(table_bbox: BBox, horizontal_lines: list[int], header_bbox: BBox | None) -> tuple[list[RowSegment], list[str]]:
    notes: list[str] = []
    boundaries = [0, *horizontal_lines, table_bbox.height]
    boundaries = sorted(set(boundaries))
    segments: list[RowSegment] = []
    header_bottom_local = (header_bbox.y2 - table_bbox.y1) if header_bbox else 0

    row_index = 1
    for y1, y2 in zip(boundaries[:-1], boundaries[1:]):
        if y2 - y1 < 8:
            continue
        global_bbox = BBox(table_bbox.x1, table_bbox.y1 + y1, table_bbox.x2, table_bbox.y1 + y2)
        is_header = header_bbox is not None and global_bbox.y2 <= header_bbox.y2 and global_bbox.y1 >= header_bbox.y1
        if not is_header and global_bbox.y1 < table_bbox.y1 + header_bottom_local:
            is_header = True
        segments.append(RowSegment(row_index=row_index, bbox=global_bbox, is_header=is_header))
        if not is_header:
            row_index += 1

    data_rows = [segment for segment in segments if not segment.is_header]
    if not data_rows:
        notes.append("no data rows detected from horizontal separators")
    return segments, notes


def _save_cell_crops(
    *,
    page_number: int,
    source_gray: np.ndarray,
    artifact_dir: Path,
    row_segments: list[RowSegment],
    column_bands: list[ColumnBand],
) -> list[CellCrop]:
    cells: list[CellCrop] = []
    cell_dir = artifact_dir / f"p{page_number:03d}_cells"
    cell_dir.mkdir(parents=True, exist_ok=True)
    data_rows = [segment for segment in row_segments if not segment.is_header]

    for data_row_index, row in enumerate(data_rows, start=1):
        for column in column_bands:
            bbox = BBox(column.x_min, row.bbox.y1, column.x_max, row.bbox.y2)
            crop = source_gray[bbox.y1 : bbox.y2, bbox.x1 : bbox.x2]
            if crop.size == 0:
                continue
            filename = f"p{page_number:03d}_r{data_row_index:03d}_c{column.column_index:02d}.png"
            target = cell_dir / filename
            cv2.imwrite(str(target), crop)
            cells.append(
                CellCrop(
                    row_index=data_row_index,
                    column_index=column.column_index,
                    canonical_field=column.canonical_field,
                    bbox=bbox,
                    image_path=str(target),
                    page_number=page_number,
                )
            )
    return cells


def _save_overlay(
    *,
    page_number: int,
    source_gray: np.ndarray,
    artifact_dir: Path,
    table_bbox: BBox | None,
    header_bbox: BBox | None,
    columns: list[ColumnBand],
    rows: list[RowSegment],
) -> str | None:
    if table_bbox is None:
        return None
    overlay = cv2.cvtColor(source_gray, cv2.COLOR_GRAY2BGR)
    cv2.rectangle(overlay, (table_bbox.x1, table_bbox.y1), (table_bbox.x2, table_bbox.y2), (0, 255, 0), 2)
    if header_bbox is not None:
        cv2.rectangle(overlay, (header_bbox.x1, header_bbox.y1), (header_bbox.x2, header_bbox.y2), (255, 0, 0), 2)
    for column in columns:
        cv2.line(overlay, (column.x_min, table_bbox.y1), (column.x_min, table_bbox.y2), (0, 165, 255), 1)
        cv2.line(overlay, (column.x_max, table_bbox.y1), (column.x_max, table_bbox.y2), (0, 165, 255), 1)
    for row in rows:
        color = (255, 0, 255) if row.is_header else (0, 255, 255)
        cv2.rectangle(overlay, (row.bbox.x1, row.bbox.y1), (row.bbox.x2, row.bbox.y2), color, 1)

    target = artifact_dir / f"p{page_number:03d}_table_parse_overlay.png"
    cv2.imwrite(str(target), overlay)
    return str(target)


def parse_table_structure(
    *,
    page_number: int,
    variants_np: dict[str, np.ndarray],
    table_detection: TableRegionDetection,
    artifact_dir: Path,
) -> TableParseResult:
    source_variant = "adaptive_binary" if "adaptive_binary" in variants_np else next(iter(variants_np.keys()), "unknown")
    binary = variants_np.get(source_variant)
    source_gray = variants_np.get("contrast")
    if source_gray is None:
        source_gray = variants_np.get("full_gray")
    if binary is None or source_gray is None:
        return TableParseResult(
            page_number=page_number,
            source_variant=source_variant,
            table_found=False,
            table_bbox=None,
            table_confidence=0.0,
            header_result=HeaderDetectionResult(False, None, "missing variants for table parsing"),
            failure_reason="required preprocessing variants are missing",
        )

    table_bbox, table_confidence = _resolve_table_bbox(table_detection, binary)
    if table_bbox is None:
        return TableParseResult(
            page_number=page_number,
            source_variant=source_variant,
            table_found=False,
            table_bbox=None,
            table_confidence=0.0,
            header_result=HeaderDetectionResult(False, None, "table region not found"),
            failure_reason="table region detection failed",
        )

    table_binary = binary[table_bbox.y1 : table_bbox.y2, table_bbox.x1 : table_bbox.x2]
    horizontal_lines = _line_positions(table_binary, axis="horizontal")
    vertical_lines = _line_positions(table_binary, axis="vertical")

    header = _detect_header(table_binary, table_bbox, horizontal_lines)
    columns, col_notes = _derive_columns(table_bbox, vertical_lines)
    rows, row_notes = _derive_rows(table_bbox, horizontal_lines, header.header_bbox)
    cells = _save_cell_crops(
        page_number=page_number,
        source_gray=source_gray,
        artifact_dir=artifact_dir,
        row_segments=rows,
        column_bands=columns,
    )
    overlay_path = _save_overlay(
        page_number=page_number,
        source_gray=source_gray,
        artifact_dir=artifact_dir,
        table_bbox=table_bbox,
        header_bbox=header.header_bbox,
        columns=columns,
        rows=rows,
    )

    notes = [*col_notes, *row_notes]
    if not notes:
        notes.append("table parsing succeeded with structural separators")

    return TableParseResult(
        page_number=page_number,
        source_variant=source_variant,
        table_found=True,
        table_bbox=table_bbox,
        table_confidence=table_confidence,
        header_result=header,
        column_bands=columns,
        row_segments=rows,
        cell_crops=cells,
        semantic_mapping_notes=notes,
        quality_indicators={
            "vertical_line_count": len(vertical_lines),
            "horizontal_line_count": len(horizontal_lines),
            "data_row_count": len([segment for segment in rows if not segment.is_header]),
            "cell_crop_count": len(cells),
        },
        debug_overlay_path=overlay_path,
    )

