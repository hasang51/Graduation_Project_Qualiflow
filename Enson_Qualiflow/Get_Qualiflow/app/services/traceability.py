from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.outcome_taxonomy import COMPLIANT, NEEDS_REVIEW, NON_COMPLIANT, aggregate_document_outcome
from app.schemas.extraction import ExtractedItem, UniversalDocumentExtraction, ValidationResult

TRACEABILITY_VERIFIED = "VERIFIED"
TRACEABILITY_UNVERIFIED = "UNVERIFIED"
TRACEABILITY_REVIEW_REASON = "traceability_unverified"
LEGACY_IDENTIFIER_REVIEW_REASON = "critical_identifier_unverified"
IDENTIFIER_CONFIDENCE_THRESHOLD = 0.80

TRACEABILITY_IDENTIFIER_GROUP_FIELDS: tuple[str, ...] = (
    "heat_number",
    "batch_number",
    "lot_number",
    "colata_number",
    "cast_number",
    "charge_number",
    "coil_number",
    "item_id",
    "pipe_id",
)
ROW_IDENTIFIER_FIELDS: tuple[str, ...] = (
    *TRACEABILITY_IDENTIFIER_GROUP_FIELDS,
    "certificate_number",
    "order_number",
)
DOCUMENT_IDENTIFIER_FIELDS: tuple[str, ...] = (
    "batch_number",
    "lot_number",
    "colata_number",
    "cast_number",
    "charge_number",
    "coil_number",
    "certificate_number",
    "order_number",
)
TRACEABILITY_GROUP_REQUIRED_FIELDS: tuple[str, ...] = (
    *TRACEABILITY_IDENTIFIER_GROUP_FIELDS,
)
TRACEABILITY_IDENTIFIER_PRIORITY: tuple[str, ...] = (
    "heat_number",
    "batch_number",
    "lot_number",
    "colata_number",
    "cast_number",
    "charge_number",
    "coil_number",
    "item_id",
    "pipe_id",
)
TRACEABILITY_LABEL_BY_FIELD: dict[str, str] = {
    "heat_number": "HEAT NO",
    "batch_number": "BATCH NO",
    "lot_number": "LOT NO",
    "colata_number": "COLATA",
    "cast_number": "CAST NO",
    "charge_number": "CHARGE NO",
    "coil_number": "COIL NO",
    "item_id": "ITEM ID",
    "pipe_id": "PIPE ID",
}


@dataclass
class IdentifierDecision:
    field: str
    value: Any = None
    confidence: float = 0.0
    source: str | None = None
    status: str = TRACEABILITY_UNVERIFIED
    raw_candidates: list[dict[str, Any]] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return self.status == TRACEABILITY_VERIFIED


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _clamp_confidence(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return None


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _accepted_entry_value_confidence(entry: Any) -> tuple[Any, float | None]:
    if isinstance(entry, dict) and "value" in entry:
        return entry.get("value"), _clamp_confidence(entry.get("confidence"))
    return entry, None


def _identifier_confidence(
    preprocessing_meta: dict[str, Any] | None,
    *,
    scope: str,
    field_name: str,
    row_index: int | None = None,
) -> float | None:
    confidence_meta = (preprocessing_meta or {}).get("identifier_confidence")
    if not isinstance(confidence_meta, dict):
        return None

    if scope == "metadata":
        metadata_values = confidence_meta.get("metadata")
        if isinstance(metadata_values, dict):
            return _clamp_confidence(metadata_values.get(field_name))
        return None

    rows = confidence_meta.get("rows")
    if not isinstance(rows, list) or row_index is None or row_index < 0 or row_index >= len(rows):
        return None
    row_values = rows[row_index]
    if isinstance(row_values, dict):
        return _clamp_confidence(row_values.get(field_name))
    return None


def _identifier_guard_events(preprocessing_meta: dict[str, Any] | None) -> list[dict[str, Any]]:
    guard = (preprocessing_meta or {}).get("identifier_guard")
    if not isinstance(guard, dict):
        return []

    events: list[dict[str, Any]] = []
    for bucket in guard.get("events") or []:
        if not isinstance(bucket, dict):
            continue
        bucket_scope = bucket.get("scope")
        bucket_row_index = bucket.get("row_index")
        suppressed = bucket.get("suppressed_identifiers")
        if isinstance(suppressed, list):
            for event in suppressed:
                if not isinstance(event, dict):
                    continue
                merged = dict(event)
                if bucket_scope is not None:
                    merged.setdefault("scope", bucket_scope)
                if bucket_row_index is not None:
                    merged.setdefault("row_index", bucket_row_index)
                events.append(merged)
        elif bucket.get("field"):
            events.append(bucket)
    return events


def _suppressed_candidates(
    preprocessing_meta: dict[str, Any] | None,
    *,
    scope: str,
    field_name: str,
    row_index: int | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for event in _identifier_guard_events(preprocessing_meta):
        if str(event.get("scope") or scope) != scope:
            continue
        event_row = event.get("row_index")
        if scope == "row" and event_row != row_index:
            continue
        if scope == "metadata" and isinstance(event_row, int):
            continue
        if event.get("field") != field_name:
            continue
        raw_value = event.get("raw_candidate")
        if _is_missing(raw_value):
            continue
        candidates.append(
            {
                "value": raw_value,
                "reason": event.get("reason") or "identifier_guard_suppressed",
                "confidence": _clamp_confidence(event.get("confidence")),
                "source": event.get("scope") or scope,
                "accepted": False,
            }
        )
    return candidates


def _raw_candidate(
    *,
    value: Any,
    reason: str,
    confidence: float | None,
    source: str,
) -> dict[str, Any]:
    return {
        "value": value,
        "reason": reason,
        "confidence": confidence,
        "source": source,
        "accepted": False,
    }


def _field_from_item_or_document(source: Any, field_name: str) -> Any:
    return getattr(source, field_name, None)


def _decide_identifier(
    *,
    field_name: str,
    value: Any,
    confidence: float | None,
    source: str,
    suppressed: list[dict[str, Any]],
) -> IdentifierDecision:
    raw_candidates = list(suppressed)
    if not _is_missing(value):
        if confidence is None:
            raw_candidates.append(
                _raw_candidate(
                    value=value,
                    reason="missing_identifier_confidence",
                    confidence=None,
                    source=source,
                )
            )
        elif confidence < IDENTIFIER_CONFIDENCE_THRESHOLD:
            raw_candidates.append(
                _raw_candidate(
                    value=value,
                    reason="low_identifier_confidence",
                    confidence=confidence,
                    source=source,
                )
            )
        else:
            return IdentifierDecision(
                field=field_name,
                value=value,
                confidence=confidence,
                source=source,
                status=TRACEABILITY_VERIFIED,
                raw_candidates=raw_candidates,
            )

    return IdentifierDecision(
        field=field_name,
        value=None,
        confidence=0.0,
        source=source,
        status=TRACEABILITY_UNVERIFIED,
        raw_candidates=raw_candidates,
    )


def _item_identifier_decision(
    item: ExtractedItem,
    *,
    field_name: str,
    row_index: int,
    preprocessing_meta: dict[str, Any] | None,
) -> IdentifierDecision:
    accepted_entry = item.accepted_identifier_values.get(field_name)
    accepted_value, accepted_confidence = _accepted_entry_value_confidence(accepted_entry)
    value = accepted_value if not _is_missing(accepted_value) else _field_from_item_or_document(item, field_name)
    confidence = accepted_confidence
    if confidence is None:
        confidence = _identifier_confidence(
            preprocessing_meta,
            scope="row",
            field_name=field_name,
            row_index=row_index,
        )
    return _decide_identifier(
        field_name=field_name,
        value=value,
        confidence=confidence,
        source=f"row:{row_index}",
        suppressed=_suppressed_candidates(
            preprocessing_meta,
            scope="row",
            field_name=field_name,
            row_index=row_index,
        ),
    )


def _document_identifier_decision(
    extraction: UniversalDocumentExtraction,
    *,
    field_name: str,
    preprocessing_meta: dict[str, Any] | None,
) -> IdentifierDecision:
    accepted_entry = extraction.accepted_identifier_values.get(field_name)
    accepted_value, accepted_confidence = _accepted_entry_value_confidence(accepted_entry)
    value = accepted_value if not _is_missing(accepted_value) else _field_from_item_or_document(extraction, field_name)
    confidence = accepted_confidence
    if confidence is None:
        confidence = _identifier_confidence(
            preprocessing_meta,
            scope="metadata",
            field_name=field_name,
        )
    return _decide_identifier(
        field_name=field_name,
        value=value,
        confidence=confidence,
        source="metadata",
        suppressed=_suppressed_candidates(
            preprocessing_meta,
            scope="metadata",
            field_name=field_name,
        ),
    )


def _combine_with_document_identifier(
    row_decision: IdentifierDecision,
    document_decision: IdentifierDecision | None,
) -> IdentifierDecision:
    if row_decision.verified:
        return row_decision
    if document_decision is not None and document_decision.verified:
        combined_raw = [*row_decision.raw_candidates, *document_decision.raw_candidates]
        return IdentifierDecision(
            field=row_decision.field,
            value=document_decision.value,
            confidence=document_decision.confidence,
            source=document_decision.source,
            status=TRACEABILITY_VERIFIED,
            raw_candidates=combined_raw,
        )
    return row_decision


def _confidence_from_decisions(decisions: dict[str, IdentifierDecision]) -> float:
    if not decisions:
        return 0.0
    group_scores = [
        decisions[field].confidence
        for field in TRACEABILITY_IDENTIFIER_PRIORITY
        if field in decisions and decisions[field].verified
    ]
    if not group_scores:
        return 0.0
    return min(group_scores)


def _raw_candidates_payload(decisions: dict[str, IdentifierDecision]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field_name, decision in decisions.items():
        if decision.raw_candidates:
            payload[field_name] = list(decision.raw_candidates)
    return payload


def _accepted_values_payload(decisions: dict[str, IdentifierDecision]) -> dict[str, Any]:
    return {
        field_name: decision.value if decision.verified else None
        for field_name, decision in decisions.items()
    }


def _is_traceability_group_field(field_name: str) -> bool:
    return field_name in TRACEABILITY_GROUP_REQUIRED_FIELDS


def _source_traceability_label(source: Any) -> str | None:
    label = getattr(source, "traceability_identifier_label", None)
    if isinstance(label, str) and label.strip():
        return label.strip()
    return None


def _allow_item_like_identifier(source: Any) -> bool:
    id_type = getattr(source, "traceability_identifier_type", None)
    if isinstance(id_type, str) and id_type.strip().lower() in {"item_id", "pipe_id"}:
        return True
    label = _source_traceability_label(source)
    if not label:
        return False
    normalized = label.lower()
    return any(token in normalized for token in ("item", "pipe", "coil id", "traceability id"))


def _group_field_eligible(source: Any, field_name: str) -> bool:
    if field_name not in {"item_id", "pipe_id"}:
        return True
    return _allow_item_like_identifier(source)


def _group_verified(decisions: dict[str, IdentifierDecision], *, source: Any) -> bool:
    for field_name in TRACEABILITY_IDENTIFIER_PRIORITY:
        decision = decisions.get(field_name)
        if decision is None or not decision.verified:
            continue
        if _group_field_eligible(source, field_name):
            return True
    return False


def _resolved_traceability_identifier(
    decisions: dict[str, IdentifierDecision],
    *,
    source: Any,
) -> tuple[str | None, str | None, str | None]:
    for field_name in TRACEABILITY_IDENTIFIER_PRIORITY:
        decision = decisions.get(field_name)
        if decision is None or not decision.verified:
            continue
        if not _group_field_eligible(source, field_name):
            continue
        raw_value = decision.value
        if _is_missing(raw_value):
            continue
        value_text = str(raw_value).strip()
        if not value_text:
            continue
        explicit_label = _source_traceability_label(source)
        if explicit_label:
            return field_name, explicit_label, value_text
        if field_name in {"batch_number", "colata_number"} and (
            decisions.get("batch_number") and decisions["batch_number"].verified
            or decisions.get("colata_number") and decisions["colata_number"].verified
        ):
            return field_name, "COLATA/BATCH n°", value_text
        return field_name, TRACEABILITY_LABEL_BY_FIELD.get(field_name, field_name), value_text
    return None, None, None


def _identifier_visibility_verified(decisions: dict[str, IdentifierDecision]) -> bool | None:
    visibility_fields = TRACEABILITY_IDENTIFIER_PRIORITY
    relevant: list[IdentifierDecision] = []
    for field_name in visibility_fields:
        decision = decisions.get(field_name)
        if decision is None:
            continue
        has_value = not _is_missing(decision.value)
        has_suppressed_candidate = bool(decision.raw_candidates)
        if has_value or has_suppressed_candidate:
            relevant.append(decision)
    if not relevant:
        return None
    return all(decision.verified for decision in relevant)


def _mechanical_row_passed(item: ExtractedItem) -> bool:
    return (
        item.validation is not None
        and item.validation.outcome == COMPLIANT
        and item.validation.is_compliant is True
    )


def _downgrade_mechanical_passed_row(item: ExtractedItem) -> None:
    if item.validation is None:
        item.validation = ValidationResult(
            is_compliant=None,
            deviations=[],
            outcome=NEEDS_REVIEW,
            rule_evidence=[],
        )
    item.validation.is_compliant = None
    item.validation.outcome = NEEDS_REVIEW
    if "Traceability identifiers require human verification." not in item.validation.deviations:
        item.validation.deviations.append("Traceability identifiers require human verification.")
    item.validation.rule_evidence.append(
        {
            "rule": "traceability.required_identifiers",
            "decision": "unverified",
            "required_fields": list(TRACEABILITY_GROUP_REQUIRED_FIELDS),
            "reason": TRACEABILITY_REVIEW_REASON,
        }
    )
    item.needs_review = True


def _aggregate_document_row_identifier(
    row_decisions_by_index: list[dict[str, IdentifierDecision]],
    *,
    field_name: str,
) -> IdentifierDecision:
    if not row_decisions_by_index:
        return IdentifierDecision(field=field_name)

    values: list[Any] = []
    confidences: list[float] = []
    raw_candidates: list[dict[str, Any]] = []
    for row_index, row_decisions in enumerate(row_decisions_by_index):
        decision = row_decisions.get(field_name)
        if decision is None or not decision.verified:
            raw_candidates.append(
                _raw_candidate(
                    value=None,
                    reason="missing_row_identifier",
                    confidence=0.0,
                    source=f"row:{row_index}",
                )
            )
            continue
        values.append(decision.value)
        confidences.append(decision.confidence)
        raw_candidates.extend(decision.raw_candidates)

    if len(values) != len(row_decisions_by_index) or not confidences:
        return IdentifierDecision(
            field=field_name,
            confidence=0.0,
            raw_candidates=raw_candidates,
        )

    unique_values: list[Any] = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    accepted_value: Any = unique_values[0] if len(unique_values) == 1 else unique_values
    return IdentifierDecision(
        field=field_name,
        value=accepted_value,
        confidence=min(confidences),
        source="rows",
        status=TRACEABILITY_VERIFIED,
        raw_candidates=raw_candidates,
    )


def validate_traceability(
    extraction: UniversalDocumentExtraction,
    preprocessing_meta: dict[str, Any] | None = None,
) -> UniversalDocumentExtraction:
    """Validate traceability separately from mechanical validation.

    Mechanical validation remains the source of threshold pass/fail decisions.
    This layer only prevents mechanically passing rows/documents from being
    auto-accepted when required identifiers are missing, low confidence, or
    present only as suppressed candidates.
    """

    document_decisions = {
        field_name: _document_identifier_decision(
            extraction,
            field_name=field_name,
            preprocessing_meta=preprocessing_meta,
        )
        for field_name in DOCUMENT_IDENTIFIER_FIELDS
    }

    any_row_downgraded = False
    row_decisions_by_index: list[dict[str, IdentifierDecision]] = []
    for row_index, item in enumerate(extraction.items):
        row_decisions: dict[str, IdentifierDecision] = {}
        for field_name in ROW_IDENTIFIER_FIELDS:
            row_decisions[field_name] = _item_identifier_decision(
                item,
                field_name=field_name,
                row_index=row_index,
                preprocessing_meta=preprocessing_meta,
            )
        for field_name in DOCUMENT_IDENTIFIER_FIELDS:
            item_decision = _item_identifier_decision(
                item,
                field_name=field_name,
                row_index=row_index,
                preprocessing_meta=preprocessing_meta,
            )
            row_decisions[field_name] = _combine_with_document_identifier(
                item_decision,
                document_decisions[field_name],
            )

        row_verified = _group_verified(row_decisions, source=item)
        item.traceability_status = TRACEABILITY_VERIFIED if row_verified else TRACEABILITY_UNVERIFIED
        item.traceability_confidence = round(_confidence_from_decisions(row_decisions), 4)
        item.accepted_identifier_values = _accepted_values_payload(row_decisions)
        item.raw_identifier_candidates = _raw_candidates_payload(row_decisions)
        item.identifier_visibility_verified = _identifier_visibility_verified(row_decisions)
        trace_type, trace_label, trace_value = _resolved_traceability_identifier(row_decisions, source=item)
        item.traceability_identifier_type = trace_type
        item.traceability_identifier_label = trace_label
        item.traceability_identifier_value = trace_value
        item.accepted_identifier_values["traceability_identifier_type"] = trace_type if row_verified else None
        item.accepted_identifier_values["traceability_identifier_label"] = trace_label if row_verified else None
        item.accepted_identifier_values["traceability_identifier_value"] = trace_value if row_verified else None

        # Invariant: If not verified, null out the user-facing field to prevent hallucination leakage.
        if not row_verified:
            for field_name in TRACEABILITY_GROUP_REQUIRED_FIELDS:
                if field_name in row_decisions and not row_decisions[field_name].verified:
                    setattr(item, field_name, None)
            item.traceability_identifier_type = None
            item.traceability_identifier_label = None
            item.traceability_identifier_value = None

        row_decisions_by_index.append(row_decisions)

        if _mechanical_row_passed(item) and not row_verified:
            _downgrade_mechanical_passed_row(item)
            any_row_downgraded = True

    for field_name in ROW_IDENTIFIER_FIELDS:
        document_decisions[field_name] = _aggregate_document_row_identifier(
            row_decisions_by_index,
            field_name=field_name,
        )

    doc_verified = _group_verified(document_decisions, source=extraction)
    extraction.traceability_status = TRACEABILITY_VERIFIED if doc_verified else TRACEABILITY_UNVERIFIED
    extraction.traceability_confidence = round(_confidence_from_decisions(document_decisions), 4)
    extraction.accepted_identifier_values = _accepted_values_payload(document_decisions)
    extraction.raw_identifier_candidates = _raw_candidates_payload(document_decisions)
    extraction.identifier_visibility_verified = (
        all(item.identifier_visibility_verified is True for item in extraction.items)
        if extraction.items
        else None
    )
    doc_trace_type, doc_trace_label, doc_trace_value = _resolved_traceability_identifier(
        document_decisions,
        source=extraction,
    )
    extraction.traceability_identifier_type = doc_trace_type
    extraction.traceability_identifier_label = doc_trace_label
    extraction.traceability_identifier_value = doc_trace_value
    extraction.accepted_identifier_values["traceability_identifier_type"] = doc_trace_type if doc_verified else None
    extraction.accepted_identifier_values["traceability_identifier_label"] = doc_trace_label if doc_verified else None
    extraction.accepted_identifier_values["traceability_identifier_value"] = doc_trace_value if doc_verified else None

    # Invariant: If not verified, null out the user-facing field to prevent hallucination leakage.
    if not doc_verified:
        for field_name in TRACEABILITY_GROUP_REQUIRED_FIELDS:
            if field_name in document_decisions and not document_decisions[field_name].verified:
                if hasattr(extraction, field_name):
                    setattr(extraction, field_name, None)
        extraction.traceability_identifier_type = None
        extraction.traceability_identifier_label = None
        extraction.traceability_identifier_value = None

    row_outcomes = [item.validation.outcome for item in extraction.items if item.validation is not None]
    extraction.outcome = aggregate_document_outcome([entry for entry in row_outcomes if entry])
    if extraction.outcome == COMPLIANT and not doc_verified:
        extraction.outcome = NEEDS_REVIEW
        extraction.is_compliant = None
        extraction.needs_review = True
        any_row_downgraded = True
    elif extraction.outcome == COMPLIANT:
        extraction.is_compliant = True
    elif extraction.outcome == NON_COMPLIANT:
        extraction.is_compliant = False
    else:
        extraction.is_compliant = None

    if any_row_downgraded:
        extraction.needs_review = True
        extraction.status = "NEEDS_REVIEW"
        extraction.review_reasons = _dedupe_preserving_order(
            [
                *extraction.review_reasons,
                TRACEABILITY_REVIEW_REASON,
                LEGACY_IDENTIFIER_REVIEW_REASON,
            ]
        )

    return extraction


__all__ = [
    "DOCUMENT_IDENTIFIER_FIELDS",
    "IDENTIFIER_CONFIDENCE_THRESHOLD",
    "LEGACY_IDENTIFIER_REVIEW_REASON",
    "ROW_IDENTIFIER_FIELDS",
    "TRACEABILITY_GROUP_REQUIRED_FIELDS",
    "TRACEABILITY_REVIEW_REASON",
    "TRACEABILITY_UNVERIFIED",
    "TRACEABILITY_VERIFIED",
    "sanitize_result_for_api_boundary",
    "sanitize_unverified_traceability_for_user",
    "validate_traceability",
]


CRITICAL_ROW_IDENTIFIER_FIELDS = (
    "heat_number",
    "heat_no",
    "batch_number",
    "lot_number",
    "colata_number",
    "cast_number",
    "charge_number",
    "coil_number",
    "item_id",
    "pipe_id",
    "pipe_coil_id",
    "traceability_identifier_value",
)

CRITICAL_DOCUMENT_IDENTIFIER_FIELDS = (
    "certificate_number",
    "order_number",
)

TRACEABILITY_BLOCKING_REASONS = {
    "critical_identifier_unverified",
    "identifier_occluded",
    "low_identifier_legibility",
    "ambiguous_identifier",
    "ocr_corruption_affecting_identifier",
    "partial_digit_visibility",
    "identifier_specific_confidence_failure",
    "visual ambiguity detected in row",
}

IDENTIFIER_SPECIFIC_CONFIDENCE_REASONS = {
    "low_identifier_confidence",
    "missing_identifier_confidence",
    "weak_identifier_evidence",
}


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _set(obj, key, value):
    if isinstance(obj, dict):
        obj[key] = value
    elif hasattr(obj, key):
        setattr(obj, key, value)


def _ensure_dict(obj, key):
    value = _get(obj, key)
    if not isinstance(value, dict):
        value = {}
        _set(obj, key, value)
    return value


def _reason_set(obj):
    reasons = set()

    for key in ("review_reasons", "validation_reasons", "evidence_gaps"):
        value = _get(obj, key)
        if isinstance(value, list):
            reasons.update(str(x) for x in value)
        elif isinstance(value, str):
            reasons.add(value)

    status = str(_get(obj, "row_status", "") or _get(obj, "status", "")).upper()
    if "NEEDS_REVIEW" in status:
        reasons.add("needs_review_status")

    return reasons


def _normalized_reason_set(obj):
    return {" ".join(str(reason).strip().lower().split()) for reason in _reason_set(obj)}


def _status_text(obj) -> str:
    status = _get(obj, "row_status")
    if status is None:
        status = _get(obj, "status")
    return str(status or "").strip().upper()


def _contains_traceability_wording(reasons: set[str]) -> bool:
    keywords = (
        "traceability",
        "identifier",
        "visual ambiguity",
        "ambiguous",
        "occluded",
        "legibility",
    )
    return any(any(keyword in reason for keyword in keywords) for reason in reasons)


def _ensure_identifier_dict(obj, snake_key: str, camel_key: str):
    value = _get(obj, snake_key)
    if isinstance(value, dict):
        return value
    alt = _get(obj, camel_key)
    if isinstance(alt, dict):
        return alt
    created: dict[str, Any] = {}
    if isinstance(obj, dict) and camel_key in obj and snake_key not in obj:
        obj[camel_key] = created
    else:
        _set(obj, snake_key, created)
    return created


def _store_raw_candidate(raw_candidates: dict[str, Any], field: str, value: Any) -> None:
    if value in (None, "", "—", "-"):
        return
    existing = raw_candidates.get(field)
    if existing is None:
        raw_candidates[field] = value
        return
    if isinstance(existing, list):
        if any(entry == value for entry in existing):
            return
        existing.append(value)


def _force_needs_review(obj) -> None:
    _set(obj, "needs_review", True)
    status = _status_text(obj)
    if "NEEDS_REVIEW" in status:
        return
    if isinstance(obj, dict):
        if "row_status" in obj:
            obj["row_status"] = "NEEDS_REVIEW"
        elif "status" in obj:
            obj["status"] = "NEEDS_REVIEW"
    elif hasattr(obj, "status"):
        setattr(obj, "status", "NEEDS_REVIEW")


def _field_aliases(field: str) -> tuple[str, ...]:
    aliases = {
        "heat_number": ("heat_number", "heat_no", "heat no", "heat"),
        "batch_number": ("batch_number", "batch_no", "batch no", "batch"),
        "lot_number": ("lot_number", "lot_no", "lot no", "lot", "lotto"),
        "colata_number": ("colata_number", "colata", "colata/batch"),
        "cast_number": ("cast_number", "cast_no", "cast no", "cast"),
        "charge_number": ("charge_number", "charge_no", "charge no", "charge"),
        "coil_number": ("coil_number", "coil_no", "coil no", "coil"),
        "item_id": ("item_id", "item", "pipe_coil_id", "coil", "pipe"),
        "pipe_id": ("pipe_id", "pipe", "pipe_coil_id"),
        "traceability_identifier_value": (
            "traceability_identifier_value",
            "traceability identifier",
            "identifier value",
        ),
        "pipe_coil_id": ("pipe_coil_id", "coil", "pipe", "item"),
        "certificate_number": ("certificate_number", "certificate", "cert"),
        "order_number": ("order_number", "order", "po"),
    }
    return aliases.get(field, (field,))


def _has_identifier_specific_reason(reasons: set[str], field: str) -> bool:
    aliases = _field_aliases(field)
    confidence_markers = ("confidence", "weak", "ocr corruption", "partial digit")
    for reason in reasons:
        if reason in TRACEABILITY_BLOCKING_REASONS:
            if reason in {"critical_identifier_unverified", "ambiguous_identifier"}:
                return True
            if reason in {"identifier_occluded", "low_identifier_legibility"}:
                if any(alias in reason for alias in aliases) or "identifier" in reason:
                    return True
            if reason in {"ocr_corruption_affecting_identifier", "partial_digit_visibility"}:
                return True
            if reason == "visual ambiguity detected in row":
                return True
        if any(token in reason for token in IDENTIFIER_SPECIFIC_CONFIDENCE_REASONS):
            if any(alias in reason for alias in aliases) or "identifier" in reason:
                return True
        if any(alias in reason for alias in aliases) and (
            "ambiguous" in reason
            or "occluded" in reason
            or "legibility" in reason
            or "unverified" in reason
            or any(marker in reason for marker in confidence_markers)
        ):
            return True
    return False


def _accepted_field_value(accepted_values: dict[str, Any], field: str) -> tuple[bool, Any]:
    if field in accepted_values:
        return True, accepted_values.get(field)
    return False, None


def _group_equivalent_verified_value(accepted_values: dict[str, Any]) -> Any:
    if "traceability_identifier_value" in accepted_values:
        value = accepted_values.get("traceability_identifier_value")
        if value not in (None, "", "—", "-"):
            return value
    for field in TRACEABILITY_IDENTIFIER_PRIORITY:
        if field not in accepted_values:
            continue
        value = accepted_values.get(field)
        if value not in (None, "", "—", "-"):
            return value
    return None


def _should_suppress_field(
    item,
    *,
    field: str,
    reasons: set[str],
    accepted_values: dict[str, Any],
) -> bool:
    has_accepted, accepted_value = _accepted_field_value(accepted_values, field)
    if has_accepted:
        if field in (*TRACEABILITY_IDENTIFIER_PRIORITY, "traceability_identifier_value"):
            if accepted_value is None:
                return _group_equivalent_verified_value(accepted_values) is None
            return False
        return accepted_value is None
    visibility_verified = _get(item, "identifier_visibility_verified")
    if visibility_verified is True:
        return False
    if visibility_verified is False:
        return _has_identifier_specific_reason(reasons, field)
    return _has_identifier_specific_reason(reasons, field)


def _document_reason_mentions_field(reasons: set[str], field: str) -> bool:
    aliases = {
        "certificate_number": ("certificate", "cert"),
        "order_number": ("order", "po"),
    }
    field_aliases = aliases.get(field, (field,))
    verification_markers = (
        "unverified",
        "unresolved",
        "ambiguous",
        "occluded",
        "illegible",
        "low",
    )
    for reason in reasons:
        if not any(alias in reason for alias in field_aliases):
            continue
        if any(marker in reason for marker in verification_markers):
            return True
    return False


def sanitize_unverified_traceability_for_user(result):
    """
    Hard API-boundary invariant:
    unverified traceability identifiers must not appear in user-facing row fields.
    Raw candidates may remain only in raw_identifier_candidates.
    """

    doc_reasons = _normalized_reason_set(result)

    items = _get(result, "items", None)
    if items is None:
        items = _get(result, "extracted_items", None)

    if isinstance(items, list):
        for item in items:
            row_reasons = _normalized_reason_set(item)
            all_reasons = row_reasons | doc_reasons
            raw_candidates = _ensure_identifier_dict(
                item,
                "raw_identifier_candidates",
                "rawIdentifierCandidates",
            )
            accepted_values = _ensure_identifier_dict(
                item,
                "accepted_identifier_values",
                "acceptedIdentifierValues",
            )
            for field in CRITICAL_ROW_IDENTIFIER_FIELDS:
                if not _should_suppress_field(
                    item,
                    field=field,
                    reasons=all_reasons,
                    accepted_values=accepted_values,
                ):
                    continue
                current_value = _get(item, field)
                _store_raw_candidate(raw_candidates, field, current_value)
                _set(item, field, None)
                accepted_values[field] = None
                _force_needs_review(item)

    document_raw_candidates = _ensure_identifier_dict(
        result,
        "raw_identifier_candidates",
        "rawIdentifierCandidates",
    )
    document_accepted_values = _ensure_identifier_dict(
        result,
        "accepted_identifier_values",
        "acceptedIdentifierValues",
    )
    for field in CRITICAL_DOCUMENT_IDENTIFIER_FIELDS:
        has_accepted, accepted_value = _accepted_field_value(document_accepted_values, field)
        if has_accepted and accepted_value is None:
            current_value = _get(result, field)
            _store_raw_candidate(document_raw_candidates, field, current_value)
            _set(result, field, None)
            document_accepted_values[field] = None
            _force_needs_review(result)
            continue
        if not _document_reason_mentions_field(doc_reasons, field):
            continue
        current_value = _get(result, field)
        _store_raw_candidate(document_raw_candidates, field, current_value)
        _set(result, field, None)
        document_accepted_values[field] = None
        _force_needs_review(result)

    return result


def sanitize_result_for_api_boundary(result: Any) -> dict[str, Any]:
    """Return a sanitized dict payload safe for API and persistence boundaries."""
    if hasattr(result, "model_dump"):
        payload = result.model_dump(mode="python")
    elif isinstance(result, dict):
        payload = dict(result)
    else:
        payload = dict(getattr(result, "__dict__", {}))
    sanitize_unverified_traceability_for_user(payload)
    return payload