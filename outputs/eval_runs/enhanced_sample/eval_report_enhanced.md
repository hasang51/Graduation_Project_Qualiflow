# QualiFlow Evaluation Report (Enhanced Layer)

- metadata: `data\gold\metadata_20.csv`
- predictions: `outputs\eval_runs\live_eval_20260612_1632`

## Accuracy Metrics

| metric | value |
| --- | --- |
| raw_exact_accuracy | 0.3619 |
| business_normalized_accuracy | 0.5762 |
| accuracy_delta | 0.2143 |
| harmless_normalization_accepts | 51 |
| true_mismatches | 81 |
| review_needed | 2 |
| critical_identifier_mismatches | 6 |

## Legacy Metrics (backward compatible)

| metric | value |
| --- | --- |
| n_documents | 20 |
| field_accuracy | 0.619 |
| critical_field_accuracy | 0.6875 |
| document_type_accuracy | 0.55 |
| processing_decision_accuracy | 0.1 |
| review_rate | 0.85 |
| unsafe_auto_accept_rate | 0.5 |
| missing_required_field_rate | 0.0446 |
| average_latency_ms | 38821.2 |
| raw_exact_accuracy | 0.3619 |
| business_normalized_accuracy | 0.5762 |
| accuracy_delta | 0.2143 |
| harmless_normalization_accepts | 51 |
| true_mismatches | 81 |
| review_needed | 2 |
| critical_identifier_mismatches | 6 |

## Matcher Breakdown

| matcher | count |
| --- | --- |
| critical_identifier_strict_match | 31 |
| date_normalized_match | 19 |
| grade_alias_match | 6 |
| list_length_mismatch | 25 |
| missing_value | 1 |
| normalized_exact_match | 40 |
| numeric_tolerance_match | 48 |
| semantic_equivalent_match | 17 |
| supplier_name_fuzzy_match | 15 |
| unit_normalized_match | 8 |

## Examples: raw fail, business pass

- `supplier_name` gold=`NOVOFIL S.p.Α.` pred=`NOVOFIL S.p.A.` matcher=`supplier_name_fuzzy_match` reason=`fuzzy score 100.0 >= accept threshold`
- `yield_strength_mpa` gold=`470` pred=`470.0` matcher=`numeric_tolerance_match` reason=`all list items matched`
- `tensile_strength_mpa` gold=`560` pred=`560.0` matcher=`numeric_tolerance_match` reason=`all list items matched`
- `elongation_percentage` gold=`26` pred=`26.0` matcher=`numeric_tolerance_match` reason=`all list items matched`
- `certificate_date` gold=`07.10.2024` pred=`07/10/2024` matcher=`date_normalized_match` reason=`iso date match`

## Examples: both fail

- `grade` gold=`NOVOFIL SG2/NOVOBRONZE SG2` pred=`NOVOFIL SG2 / NOVOBRONZE SG2` reason=`list item mismatch`
- `review_required` gold=`False` pred=`True` reason=`no matcher accepted`
- `grade` gold=`1.4541/321 1.4878/321H` pred=`1.4541/321 1.4878/321H UNS S32100` reason=`list item mismatch`
- `tensile_strength_mpa` gold=`638` pred=`581.0` reason=`list item mismatch`
- `elongation_percentage` gold=`52` pred=`72.0` reason=`list item mismatch`

## Examples: critical identifier failures

- `grade` gold=`NOVOFIL SG2/NOVOBRONZE SG2` pred=`NOVOFIL SG2 / NOVOBRONZE SG2` reason=`list item mismatch`
- `grade` gold=`1.4541/321 1.4878/321H` pred=`1.4541/321 1.4878/321H UNS S32100` reason=`list item mismatch`
- `tensile_strength_mpa` gold=`638` pred=`581.0` reason=`list item mismatch`
- `elongation_percentage` gold=`52` pred=`72.0` reason=`list item mismatch`
- `heat_number` gold=`210219AED2-01` pred=`Z10210-04` reason=`list item mismatch`

## Method

The evaluation layer reports both `raw_exact_accuracy` (literal string equality) and `business_normalized_accuracy` (field-aware deterministic matchers). Critical identifiers use strict matching only. This measures evaluation quality and extraction comparability — not model safety routing.

