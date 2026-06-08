# Jury Architecture Summary

## Where the Intelligence Lives

The system is neuro-symbolic:

- **Neural part**: multimodal extraction (Claude) reads heterogeneous certificate layouts.
- **Symbolic part**: deterministic normalization, routing, validation, and review policy enforce auditable decision logic.

## Pipeline Boundary

1. Upload and profiling
2. Explicit route selection (A/B/C/D)
3. Image/variant extraction
4. Semantic normalization + context propagation
5. Deterministic validator
6. Confidence/review policy
7. Explanation payload + UI panel

Deterministic validation begins at the validator stage after semantic normalization/context propagation.

## Why Review Exists

Review is an explicit safety mechanism, not a fallback bug:

- unresolved spec family
- unsupported rule family
- ambiguous numeric normalization
- evidence conflict
- severe scan quality

The system prefers unresolved/review over false certainty.

## Why This Is Generic

- no filename/vendor-specific branching
- ontology/alias-driven field and grade mapping
- route decisions based on measurable document profile metrics
- propagation and evidence logic based on canonical fields and identifiers

This supports heterogeneous COA/MTC/inspection certificates while staying deterministic and explainable.
