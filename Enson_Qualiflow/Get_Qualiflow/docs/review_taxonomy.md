# Review Taxonomy

Review decisions are now structured (`app/services/review_policy.py`) and aligned with canonical outcomes (`app/domain/outcome_taxonomy.py`).

## Canonical Outcomes

- `COMPLIANT`
- `NON_COMPLIANT`
- `NOT_VALIDATED`
- `NEEDS_REVIEW`
- `UNRESOLVED_SPEC`
- `UNSUPPORTED_SPEC_FAMILY`

## Core Semantics

- unresolved or unsupported specs are never auto-labeled as non-compliant
- skipped validation is `NOT_VALIDATED`
- true rule breaches after confident spec resolution are `NON_COMPLIANT`

## Review Decision Structure

`ReviewDecision` returns:

- `review_required`
- `review_reasons`
- `blocking_reasons`
- `evidence_gaps`
- `recommended_reviewer_focus`
- `all_reasons`

This structure is used directly in the explanation payload and frontend explanation panel.
