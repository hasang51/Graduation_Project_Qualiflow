# Table Parsing Stage (Stage 4)

## What this stage adds

Stage 4 introduces deterministic structural segmentation for table-like manufacturing certificate pages.

Instead of relying only on free-form whole-page interpretation, the system now extracts:

- main table region
- header row band
- ordered column x-ranges
- row boundaries
- per-cell crops with geometry metadata

## Why this is required

Thesis-grade reliability requires explainable table geometry:

- "this x-range corresponds to `heat_number`"
- "this cell crop belongs to row 7 / `tensile_strength_mpa`"

This structural layer supports table-aware Claude extraction by producing cropped, geometry-labeled images the vision model can reason about alongside the full page.

## How detection works

Implemented in `app/services/table_parser.py`.

High-level flow:

1. Use adaptive binary variant as primary structural source.
2. Resolve table region:
   - prefer existing table detector output
   - fallback to large contour-based table bbox if needed
3. Detect horizontal/vertical separators via morphology line extraction.
4. Infer header band:
   - first horizontal grid band when available
   - top-band fallback with explicit unresolved reason otherwise
5. Derive ordered column bands from vertical separators.
6. Derive row segments from horizontal separators (header vs data rows).
7. Generate per-cell crops from row x column intersections.
8. Save overlay image and serialized parse metadata.

## Structural outputs

Typed outputs include:

- `TableParseResult`
- `HeaderDetectionResult`
- `ColumnBand`
- `RowSegment`
- `CellCrop`
- `BBox`

Each parse result is serializable and persisted inside preprocessing metadata:

- `pages[n].table_parsing`

## Semantic column anchoring

Stage 4 applies positional mapping to target canonical columns:

- `item_id`
- `heat_number`
- `grade`
- `weight_or_length`
- `yield_strength_mpa`
- `tensile_strength_mpa`
- `elongation_percentage`

If geometry confidence is weak, mapping notes capture uncertainty (no fake certainty).

## Generated artifacts

For successful parsing:

- overlay image:
  - `pXXX_table_parse_overlay.png`
  - shows table bbox, header band, column boundaries, row boxes
- per-cell crops:
  - `pXXX_cells/pXXX_rYYY_cZZ.png`

All artifacts are saved in existing artifact storage paths.

## Integration notes

- Table parsing runs inside `preprocess_pdf(...)` after adaptive variant generation.
- Existing extraction API shape remains unchanged.
- Existing pipeline behavior is preserved; parsing failures degrade gracefully with structured failure metadata.

