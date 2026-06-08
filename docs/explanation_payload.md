# Explanation Payload

The extraction response now includes additive explainability fields:

- `outcome`
- `confidence_breakdown`
- `explanation`

## `confidence_breakdown`

Current subcomponents:

- `extraction_confidence`
- `normalization_confidence`
- `spec_resolution_confidence`
- `validation_confidence`
- `overall_decision_confidence`

This makes it visible that high extraction confidence does not automatically imply high compliance certainty.

## `explanation`

Structured sections:

- `document_profile`
- `route_decision`
- `validation_outcome`
- `review_policy`
- `evidence_propagation_notes`
- `unresolved_or_ambiguous`
- `confidence_breakdown`

These sections are displayed in the frontend explanation panel and persisted for debugging/jury narrative.
