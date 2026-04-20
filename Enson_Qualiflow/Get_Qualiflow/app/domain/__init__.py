from app.domain.field_mapping_registry import (
    CANONICAL_FIELDS,
    explain_mapping,
    get_canonical_definition,
    get_registry_snapshot,
    normalize_header,
    resolve_canonical_field,
)

__all__ = [
    "CANONICAL_FIELDS",
    "normalize_header",
    "resolve_canonical_field",
    "get_canonical_definition",
    "get_registry_snapshot",
    "explain_mapping",
]
