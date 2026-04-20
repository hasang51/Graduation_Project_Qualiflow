from __future__ import annotations

import json
import logging
from typing import Any

import anthropic
from fastapi import HTTPException

from app.config import settings
from app.domain.field_mapping_registry import CANONICAL_FIELDS, explain_mapping, get_registry_snapshot, resolve_canonical_field
from app.domain.header_propagation import apply_updates, propagate_to_rows
from app.domain.numeric_parser import parse_mechanical_properties
from app.schemas.extraction import ExtractedItem, MechanicalProperties, UniversalDocumentExtraction
from app.services.confidence import normalize_confidence
from app.services.document_profiler import DocumentProfile
from app.services.preprocessing import EncodedVariant, ProcessedPage
from app.services.review_policy import apply_review_policy
from app.services.validator import validate_document

logger = logging.getLogger("qualiflow.pipeline")


METADATA_TOOL: dict[str, Any] = {
    "name": "submit_document_metadata",
    "description": "Submit top-level document metadata only.",
    "input_schema": {
        "type": "object",
        "properties": {
            "supplier_name": {"type": "string"},
            "document_type": {"type": "string"},
            "certificate_date": {"type": ["string", "null"]},
            "ai_analysis_remarks": {"type": ["string", "null"]},
            "confidence_score": {"type": "number"},
        },
        "required": ["supplier_name", "document_type", "confidence_score"],
    },
}

ITEM_TOOL: dict[str, Any] = {
    "name": "submit_line_items",
    "description": "Submit every extracted line item with strict nulls for unknown values.",
    "input_schema": {
        "type": "object",
        "properties": {
            "total_items_detected": {"type": "integer"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": ["string", "null"]},
                        "heat_number": {"type": ["string", "null"]},
                        "grade": {"type": ["string", "null"]},
                        "weight_or_length": {"type": ["string", "null"]},
                        "mechanical_properties": {
                            "type": ["object", "null"],
                            "properties": {
                                "yield_strength_mpa": {"type": ["number", "null"]},
                                "tensile_strength_mpa": {"type": ["number", "null"]},
                                "elongation_percentage": {"type": ["number", "null"]},
                            },
                        },
                        "row_confidence": {"type": ["number", "null"]},
                    },
                },
            },
        },
        "required": ["total_items_detected", "items"],
    },
}

METADATA_PROMPT = (
    "You are Stage A of an industrial document extraction pipeline. "
    "Use full-page document context to extract only document-level metadata. "
    "Do not guess unreadable text. Use null where uncertain. "
    "Recognizing the document type does not imply that tabular row values are readable. "
    "Confidence_score in this stage must reflect document-level understanding only, not row-level extraction quality. "
    "In ai_analysis_remarks, clearly explain when document understanding is acceptable but row extraction may be weak due to blur, scan noise, missing table clarity, or unreadable cells. "
    "Return only supplier_name, document_type, certificate_date, ai_analysis_remarks, confidence_score."
)

ITEM_PROMPT = (
    "You are Stage B of an industrial document extraction pipeline. "
    "Extract table line items from table-focused images. "
    "Priority is precision over recall for noisy scans. "
    "If a cell is unreadable, set that field to null. "
    "Do not infer a row value unless the cell is visually supported in the image. "
    "Do not infer, repair, or guess ambiguous row IDs, heat numbers, grades, weights, lengths, or mechanical values from domain intuition. "
    "Preserve row structure only when row boundaries or cell contents are actually visible. "
    "Do not create placeholder rows for implied totals or partially imagined table structure. "
    "If no reliable rows are visible, return total_items_detected as 0 and items as an empty array. "
    "Row confidence must be low when text is degraded, cell boundaries are unclear, or digits are ambiguous."
)


def _build_diagnostic_summary(
    *,
    pages: list[ProcessedPage],
    metadata: dict[str, Any],
    items: list[ExtractedItem],
    total_items_detected: int,
    confidence_score: float,
) -> dict[str, Any]:
    document_type = str(metadata.get("document_type", "Unknown document"))
    supplier_name = str(metadata.get("supplier_name", "Unknown supplier"))
    return {
        "document_understood": document_type != "Unknown document" or supplier_name != "Unknown supplier",
        "rows_extracted": len(items),
        "has_table_like_structure": any(page.table_crop_available for page in pages),
        "document_type": document_type,
        "total_items_detected": total_items_detected,
        "items_array_length": len(items),
        "confidence_score_from_model": confidence_score,
    }


def _anthropic_client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required.")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _image_block(image: EncodedVariant) -> dict[str, Any]:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": image.media_type, "data": image.data},
    }


def _metadata_blocks(pages: list[ProcessedPage]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    seen_variant_keys: set[str] = set()

    for page in pages[: settings.max_pages_for_llm]:
        primary = page.full_page_variant_name if page.full_page_variant_name in page.variants else "contrast"
        if primary not in page.variants:
            primary = "full_gray"
        _append_unique_block(blocks, seen_variant_keys, page.variants[primary], f"p{page.page_number}:{primary}")

        # Phase 2 cost fix: only add full_gray for page 1 when it differs
        # from the already-added primary variant, to avoid sending the same
        # image twice.
        if page.page_number == 1 and primary != "full_gray" and "full_gray" in page.variants:
            _append_unique_block(blocks, seen_variant_keys, page.variants["full_gray"], f"p{page.page_number}:full_gray")

    blocks.append({"type": "text", "text": "Extract document-level metadata only."})
    return blocks


def _row_extraction_blocks(pages: list[ProcessedPage]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    seen_variant_keys: set[str] = set()

    for page in pages[: settings.max_pages_for_llm]:
        preferred = page.selected_variants if page.selected_variants else []
        for variant_name in preferred:
            if variant_name in page.variants:
                _append_unique_block(blocks, seen_variant_keys, page.variants[variant_name], f"p{page.page_number}:{variant_name}")

        if page.table_crop_available:
            # Table crop + adaptive binary are most informative for row extraction.
            for vname in ("table_crop", "adaptive_binary"):
                if vname in page.variants:
                    _append_unique_block(blocks, seen_variant_keys, page.variants[vname], f"p{page.page_number}:{vname}")
        else:
            # No table crop: use one clean full-page view only.
            full_page_name = page.full_page_variant_name if page.full_page_variant_name in page.variants else "contrast"
            if full_page_name in page.variants:
                _append_unique_block(blocks, seen_variant_keys, page.variants[full_page_name], f"p{page.page_number}:{full_page_name}")

    return blocks


def _append_unique_block(
    blocks: list[dict[str, Any]],
    seen: set[str],
    image: "EncodedVariant",
    key: str,
) -> None:
    """Append an image block only if we haven't already included this key."""
    if key not in seen:
        seen.add(key)
        blocks.append(_image_block(image))


def _items_blocks(pages: list[ProcessedPage]) -> list[dict[str, Any]]:
    blocks = _row_extraction_blocks(pages)
    blocks.append({"type": "text", "text": "Extract line items from visible tables."})
    return blocks


def _extract_usage(response: Any) -> dict[str, int]:
    """Pull token usage from an Anthropic response object safely."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0}
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
    }


def _run_metadata_extraction(
    client: anthropic.Anthropic,
    pages: list[ProcessedPage],
) -> tuple[dict[str, Any], dict[str, int]]:
    """Returns ``(metadata_dict, usage_dict)``."""
    metadata_resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2048,
        temperature=0.0,
        system=METADATA_PROMPT,
        messages=[{"role": "user", "content": _metadata_blocks(pages)}],
        tools=[METADATA_TOOL],
        tool_choice={"type": "tool", "name": "submit_document_metadata"},
    )
    return _extract_tool_input(metadata_resp, "submit_document_metadata"), _extract_usage(metadata_resp)


def _run_row_extraction(
    client: anthropic.Anthropic,
    pages: list[ProcessedPage],
    metadata: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    """Returns ``(item_payload_dict, usage_dict)``."""
    document_type = metadata.get("document_type", "Unknown document")
    supplier_name = metadata.get("supplier_name", "Unknown supplier")
    row_prompt_context = (
        f"Document type identified in Stage A: {document_type}. "
        f"Supplier identified in Stage A: {supplier_name}. "
        "Use that only as context. Do not invent missing line items or unreadable cell values."
    )
    blocks = _items_blocks(pages)
    blocks.append({"type": "text", "text": row_prompt_context})
    item_resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=4096,
        temperature=0.0,
        system=ITEM_PROMPT,
        messages=[{"role": "user", "content": blocks}],
        tools=[ITEM_TOOL],
        tool_choice={"type": "tool", "name": "submit_line_items"},
    )
    return _extract_tool_input(item_resp, "submit_line_items"), _extract_usage(item_resp)


def _extract_tool_input(response: Any, tool_name: str) -> dict[str, Any]:
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input
    raise HTTPException(status_code=502, detail=f"LLM response missing tool output: {tool_name}")


def _value_from_canonical_or_alias(payload: dict[str, Any], canonical_field: str) -> Any:
    if canonical_field in payload:
        return payload.get(canonical_field)
    for key, value in payload.items():
        if resolve_canonical_field(str(key)) == canonical_field:
            return value
    return None


def _mapping_diagnostics(metadata: dict[str, Any], items_raw: list[dict[str, Any]]) -> dict[str, Any]:
    observed_headers: list[str] = list(metadata.keys())
    for row in items_raw[:1]:
        observed_headers.extend(str(key) for key in row.keys())
        if isinstance(row.get("mechanical_properties"), dict):
            observed_headers.extend(str(key) for key in row["mechanical_properties"].keys())

    explanations = [explain_mapping(header) for header in observed_headers]
    resolved = [entry for entry in explanations if entry.get("matched_canonical_field")]
    unresolved = [entry for entry in explanations if not entry.get("matched_canonical_field")]
    return {
        "registry_version": "v1",
        "canonical_fields": sorted(CANONICAL_FIELDS.keys()),
        "resolved_headers_count": len(resolved),
        "unresolved_headers_count": len(unresolved),
        "resolved_headers": resolved,
        "unresolved_headers": unresolved,
        "registry_snapshot": get_registry_snapshot(),
    }


def _normalize_row_dict(item_raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten an LLM item payload into the canonical-key dict shape.

    Numeric parsing and header propagation operate on plain dicts so the
    validator and schema stay decoupled from Anthropic's exact key variance.
    """

    mp_raw = item_raw.get("mechanical_properties")
    mp_payload: dict[str, Any] | None = None
    if isinstance(mp_raw, dict):
        mp_payload = {
            "yield_strength_mpa": _value_from_canonical_or_alias(mp_raw, "yield_strength_mpa"),
            "tensile_strength_mpa": _value_from_canonical_or_alias(mp_raw, "tensile_strength_mpa"),
            "elongation_percentage": _value_from_canonical_or_alias(mp_raw, "elongation_percentage"),
        }

    row_conf = item_raw.get("row_confidence")
    if not isinstance(row_conf, (float, int)):
        row_conf = None
    elif row_conf < 0 or row_conf > 1:
        row_conf = None

    return {
        "item_id": _value_from_canonical_or_alias(item_raw, "item_id"),
        "heat_number": _value_from_canonical_or_alias(item_raw, "heat_number"),
        "grade": _value_from_canonical_or_alias(item_raw, "grade"),
        "weight_or_length": _value_from_canonical_or_alias(item_raw, "weight_or_length"),
        "mechanical_properties": mp_payload,
        "row_confidence": row_conf,
    }


def _apply_numeric_parser(
    rows: list[dict[str, Any]],
    preprocessing_meta: dict[str, Any],
) -> list[str]:
    """Normalise numeric values in-place.

    Returns a list of structured review-reason tokens (``numeric_uncertain:<field>``
    and ``numeric_promoted_thousands:<field>``) to surface to the caller.
    """

    trace: list[dict[str, Any]] = []
    tokens: list[str] = []
    for index, row in enumerate(rows):
        mp_raw = row.get("mechanical_properties")
        if not isinstance(mp_raw, dict):
            continue
        values, row_trace = parse_mechanical_properties(mp_raw)
        row["mechanical_properties"] = values
        serialisable_trace = {key: parsed.to_dict() for key, parsed in row_trace.items()}
        trace.append({"row_index": index, "fields": serialisable_trace})
        for field_name, parsed in row_trace.items():
            if parsed.promoted_thousands:
                tokens.append(f"numeric_promoted_thousands:{field_name}")
            if parsed.uncertain and parsed.value is not None:
                tokens.append(f"numeric_uncertain:{field_name}")
    preprocessing_meta["numeric_parser_trace"] = trace
    return tokens


def _apply_header_propagation(
    rows: list[dict[str, Any]],
    metadata: dict[str, Any],
    ai_remarks: str | None,
    preprocessing_meta: dict[str, Any],
) -> list[str]:
    """Back-fill missing row grades from a strong header grade.

    Returns structured review tokens describing propagation conflicts.
    """

    result = propagate_to_rows(rows, metadata=metadata, ai_remarks=ai_remarks)
    preprocessing_meta["header_propagation"] = result.to_dict()
    apply_updates(rows, result)
    return list(result.conflicts)


def _row_dict_to_item(row: dict[str, Any]) -> ExtractedItem:
    mp_raw = row.get("mechanical_properties")
    mechanical = None
    if isinstance(mp_raw, dict):
        mechanical = MechanicalProperties(
            yield_strength_mpa=mp_raw.get("yield_strength_mpa"),
            tensile_strength_mpa=mp_raw.get("tensile_strength_mpa"),
            elongation_percentage=mp_raw.get("elongation_percentage"),
        )
    return ExtractedItem(
        item_id=row.get("item_id"),
        heat_number=row.get("heat_number"),
        grade=row.get("grade"),
        weight_or_length=row.get("weight_or_length"),
        mechanical_properties=mechanical,
        row_confidence=row.get("row_confidence"),
        grade_provenance=row.get("grade_provenance") or ("row" if row.get("grade") else None),
    )


def run_multi_stage_extraction(
    pages: list[ProcessedPage],
    preprocessing_meta: dict[str, Any],
    profile: DocumentProfile | None = None,
) -> UniversalDocumentExtraction:
    client = _anthropic_client()
    try:
        metadata, usage_a = _run_metadata_extraction(client, pages)
        item_payload, usage_b = _run_row_extraction(client, pages, metadata)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("LLM extraction failed.")
        raise HTTPException(status_code=502, detail=f"Vision extraction failed: {exc}") from exc

    # Store token usage for budget tracking and thesis reporting.
    combined_usage = {
        "stage_a_input_tokens": usage_a["input_tokens"],
        "stage_a_output_tokens": usage_a["output_tokens"],
        "stage_b_input_tokens": usage_b["input_tokens"],
        "stage_b_output_tokens": usage_b["output_tokens"],
        "total_input_tokens": usage_a["input_tokens"] + usage_b["input_tokens"],
        "total_output_tokens": usage_a["output_tokens"] + usage_b["output_tokens"],
        "pages_sent": len(pages),
    }
    preprocessing_meta["llm_usage"] = combined_usage
    logger.info("LLM usage: %s", combined_usage)

    items_raw = item_payload.get("items", [])
    items_dicts = [_normalize_row_dict(row) for row in items_raw if isinstance(row, dict)]
    numeric_tokens = _apply_numeric_parser(items_dicts, preprocessing_meta)
    propagation_tokens = _apply_header_propagation(
        items_dicts,
        metadata=metadata,
        ai_remarks=metadata.get("ai_analysis_remarks") if isinstance(metadata, dict) else None,
        preprocessing_meta=preprocessing_meta,
    )
    items = [_row_dict_to_item(row) for row in items_dicts]
    preprocessing_meta["field_mapping_diagnostics"] = _mapping_diagnostics(
        metadata=metadata,
        items_raw=[row for row in items_raw if isinstance(row, dict)],
    )
    raw_model_confidence = float(metadata.get("confidence_score", 0.0))
    raw_model_confidence = max(0.0, min(raw_model_confidence, 1.0))
    raw_reported_total_items = int(item_payload.get("total_items_detected", len(items)))
    diagnostic_summary = _build_diagnostic_summary(
        pages=pages,
        metadata=metadata,
        items=items,
        total_items_detected=raw_reported_total_items,
        confidence_score=raw_model_confidence,
    )
    preprocessing_meta["diagnostic_summary"] = diagnostic_summary
    logger.info("Extraction diagnostic summary: %s", json.dumps(diagnostic_summary, ensure_ascii=False))
    extraction = UniversalDocumentExtraction(
        supplier_name=str(metadata.get("supplier_name", "Unknown supplier")),
        document_type=str(metadata.get("document_type", "Unknown document")),
        certificate_date=metadata.get("certificate_date"),
        total_items_detected=raw_reported_total_items,
        items=items,
        confidence_score=raw_model_confidence,
        raw_model_confidence=raw_model_confidence,
        ai_analysis_remarks=metadata.get("ai_analysis_remarks"),
    )

    # Seed review reasons from numeric parser + header propagation before
    # validation so the validator sees a coherent, pre-normalised state.
    if numeric_tokens or propagation_tokens:
        extraction.review_reasons = sorted(set([*extraction.review_reasons, *numeric_tokens, *propagation_tokens]))
        extraction.needs_review = extraction.needs_review or bool(numeric_tokens or propagation_tokens)

    extraction = validate_document(extraction)

    remarks = str(extraction.ai_analysis_remarks or "").lower()
    if any(token in remarks for token in ("blur", "noise", "unreadable", "unclear")):
        extraction.review_reasons.append("document readability concerns noted in analysis remarks")
        extraction.needs_review = True

    if any(item.row_confidence is not None and item.row_confidence < settings.review_confidence_threshold for item in extraction.items):
        extraction.review_reasons.append("low-confidence rows detected")
    if len(extraction.items) == 0:
        extraction.review_reasons.append("extraction structure is incomplete")

    confidence_assessment = normalize_confidence(
        extraction=extraction,
        preprocessing_meta=preprocessing_meta,
        raw_reported_total_items=raw_reported_total_items,
        review_confidence_threshold=settings.review_confidence_threshold,
    )
    extraction.confidence_score = confidence_assessment.final_confidence
    extraction.review_reasons = confidence_assessment.review_reasons
    extraction.needs_review = confidence_assessment.status == "NEEDS_REVIEW"
    extraction.status = confidence_assessment.status
    preprocessing_meta["confidence_assessment"] = confidence_assessment.metrics
    logger.info("Confidence assessment: %s", json.dumps(confidence_assessment.metrics, ensure_ascii=False))

    review_decision = apply_review_policy(
        extraction,
        profile=profile,
        preprocessing_meta=preprocessing_meta,
        review_confidence_threshold=settings.review_confidence_threshold,
    )
    preprocessing_meta["review_policy"] = review_decision.to_dict()
    logger.info(
        "Review policy: needs_review=%s structured_reasons=%s",
        review_decision.needs_review,
        review_decision.structured_reasons,
    )
    return extraction
