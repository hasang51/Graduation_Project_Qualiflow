# Domain Schema Stabilization

## Why this exists

QualiFlow extracts compliance data from scanned industrial certificates where the same business concept appears under different headers.  
This module introduces a deterministic canonical vocabulary so extraction semantics are stable and auditable.

Without this layer, row semantics can drift as header variants change between document families.

## Canonical fields

- `supplier_name`
- `document_type`
- `certificate_date`
- `item_id`
- `heat_number`
- `grade`
- `weight_or_length`
- `yield_strength_mpa`
- `tensile_strength_mpa`
- `elongation_percentage`

## Synonym mapping rules

Core stabilized mappings:

- `HEAT NO`, `MELT NO`, `DOKUM NO`, `DÖKÜM NO`, `SCHMELZE NO` -> `heat_number`
- `BATCH NO`, `BATCH NUMBER` -> `batch_number`
- `LOT NO`, `LOT NUMBER` -> `lot_number`
- `CAST NO`, `CAST NUMBER` -> `cast_number`
- `COLATA`, `COLATA NO` -> `colata_number`
- `CHARGE NO`, `CHARGE NUMBER` -> `charge_number`
- `SIZE`, `EBAT`, `ITEM` -> `item_id`
- `LENGTH`, `UZUNLUK`, `WEIGHT` -> `weight_or_length`
- `YIELD TS`, `RE`, `RP0.2` -> `yield_strength_mpa`
- `TENSILE TS`, `RM` -> `tensile_strength_mpa`
- `ELONGATION`, `A%` -> `elongation_percentage`

The registry in `app/domain/field_mapping_registry.py` is machine-readable and includes:

- canonical field name
- description
- business meaning
- value type
- category
- units
- synonyms
- normalized variants

## Normalization behavior

Headers are normalized before matching:

- uppercase conversion
- whitespace collapse
- punctuation cleanup
- Turkish character normalization (`DÖKÜM` -> `DOKUM`)
- decimal punctuation normalization (`RP 0,2` -> `RP0.2`)

Normalization is controlled to avoid unrelated header collisions.

## How to extend for new document families

1. Add synonym/header variants to the relevant field in `CANONICAL_FIELDS`.
2. Keep business meaning unchanged unless domain requirements really change.
3. Add unit tests for each new variant in `tests/test_field_mapping_registry.py`.
4. Preserve canonical names to avoid breaking downstream compatibility.

## Deterministic explainability

Question: **"Why did the system call this field `heat_number`?"**

Deterministic answer:

- `resolve_canonical_field("HEAT NO")` returns `heat_number`.
- `explain_mapping("HEAT NO")` returns structured evidence:
  - input header
  - normalized header
  - matched canonical field
  - matched synonym
  - confidence
  - match reason

This ensures schema mapping can be traced and audited in diagnostics.

