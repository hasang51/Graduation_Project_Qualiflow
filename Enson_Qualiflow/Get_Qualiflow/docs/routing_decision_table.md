# Routing Decision Table

The extraction router is now explicit and inspectable (`app/services/extraction_router.py`).

## Profiler Classes

- `digital_clean`
- `scan_clean`
- `noisy_scan`
- `severe_scan`

## Explicit Paths

| Route | Trigger | Runtime Route | Review Bias |
| --- | --- | --- | --- |
| `path_a_digital_pdf` | clean text layer + acceptable quality | `native_multimodal` | no |
| `path_b_clean_scan` | scan but clean | `rendered_multimodal` | no |
| `path_c_noisy_scan` | degraded but still extractable | `preprocessed_multimodal` | conditional |
| `path_d_severe_scan` | severe blur/noise or very poor readability | `preprocessed_multimodal` (minimal attempt) | yes |

## Explainability Payload

Each decision returns:

- `selected_route`
- `runtime_route`
- `reason_codes`
- `triggering_features`
- `expected_strategy`
- `review_first_bias`

This is stored in preprocessing metadata and returned through the explanation payload for UI and jury walkthrough.
