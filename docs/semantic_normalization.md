# Semantic Normalization

QualiFlow now uses a dedicated semantic normalization layer (`app/services/semantic_normalizer.py`) instead of ad hoc regex handling in unrelated modules.

## What It Normalizes

- Field aliases via `app/domain/field_synonym_registry.py`
  - Examples: `Heat No`, `Cast No`, `Schmelze No` -> `heat_number`
- Grade aliases + composite grade tokens via `app/domain/grade_alias_registry.py`
  - Examples: `304/304L 1.4301/1.4307`, `316/316L 1.4401/1.4404`
- Key formatting drift
  - case normalization
  - punctuation/whitespace normalization
  - conservative ambiguity flags

## Output Shape

For each row we keep:

- raw value
- normalized tokens
- candidate canonical forms
- unresolved/ambiguous metadata

This metadata is persisted in preprocessing diagnostics and exposed to review/explanation paths.

## Conservative Rule

Ambiguous grade/spec interpretation is never silently collapsed into a single canonical value. Ambiguous or unresolved resolution is forwarded to review-safe outcomes.
