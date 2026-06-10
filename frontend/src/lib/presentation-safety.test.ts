import {
  formatSyntheticRowRef,
  getPresentationSpecificationCheckDisplay,
  isItemMechanicallyIncomplete,
  isMechanicalVerificationIncomplete,
  MECHANICAL_INCOMPLETE_REASON,
  resolveDecisionConfidence,
  resolveItemRefCellValue,
  resolveItemRefColumnHeader,
  shouldUseSyntheticRowRef,
} from './presentation-safety'
import type { ExtractedItem, ExtractionResponse } from '../types/qualiflow'

function makeItem(overrides: Partial<ExtractedItem> = {}): ExtractedItem {
  return {
    item_id: null,
    heat_number: null,
    batch_number: null,
    certificate_number: null,
    order_number: null,
    grade: 'S355',
    weight_or_length: null,
    mechanical_properties: {
      yield_strength_mpa: 355,
      tensile_strength_mpa: 510,
      elongation_percentage: 22,
    },
    validation: { is_compliant: true, deviations: [], outcome: 'COMPLIANT' },
    ...overrides,
  }
}

function makeExtraction(overrides: Partial<ExtractionResponse> = {}): ExtractionResponse {
  return {
    supplier_name: 'Supplier',
    document_type: 'MTC',
    batch_number: null,
    certificate_number: null,
    order_number: null,
    certificate_date: null,
    total_items_detected: 1,
    items: [makeItem()],
    confidence_score: 0.7,
    ai_analysis_remarks: null,
    is_compliant: true,
    outcome: 'COMPLIANT',
    ...overrides,
  }
}

if (isMechanicalVerificationIncomplete(makeExtraction())) {
  throw new Error('Expected complete mechanical data to pass verification guard.')
}

if (
  !isMechanicalVerificationIncomplete(
    makeExtraction({
      review_reasons: ['missing_critical_field:yield_strength'],
    }),
  )
) {
  throw new Error('Expected missing_critical_field review reason to trigger guard.')
}

if (
  !isMechanicalVerificationIncomplete(
    makeExtraction({
      items: [
        makeItem({
          mechanical_properties: {
            yield_strength_mpa: null,
            tensile_strength_mpa: 510,
            elongation_percentage: 22,
          },
        }),
      ],
    }),
  )
) {
  throw new Error('Expected null yield strength to trigger guard.')
}

if (
  !isMechanicalVerificationIncomplete(
    makeExtraction({
      items: [
        makeItem({
          validation: {
            is_compliant: null,
            deviations: ['Yield missing - cannot verify.'],
            outcome: 'NOT_VALIDATED',
          },
        }),
      ],
    }),
  )
) {
  throw new Error('Expected missing-cannot-verify deviation to trigger guard.')
}

if (
  !isItemMechanicallyIncomplete(makeItem(), ['missing_critical_field:elongation'])
) {
  throw new Error('Expected document review reason to affect row guard.')
}

const incompleteDisplay = getPresentationSpecificationCheckDisplay(
  makeExtraction({
    review_reasons: ['missing_critical_field:tensile_strength'],
  }),
)
if (incompleteDisplay.label !== 'Incomplete' || incompleteDisplay.reason !== MECHANICAL_INCOMPLETE_REASON) {
  throw new Error('Expected presentation spec check to show Incomplete with reason.')
}

const completeDisplay = getPresentationSpecificationCheckDisplay(makeExtraction())
if (completeDisplay.label !== 'Compliant') {
  throw new Error('Expected complete data to show Compliant presentation label.')
}

const decisionConfidence = resolveDecisionConfidence(
  makeExtraction({
    confidence_score: 0.7,
    confidence_breakdown: { overall_decision_confidence: 0.55, extraction_confidence: 0.95 },
  }),
)
if (decisionConfidence !== 0.55) {
  throw new Error('Expected overall_decision_confidence to take precedence.')
}

const fallbackConfidence = resolveDecisionConfidence(
  makeExtraction({ confidence_score: 0.7, confidence_breakdown: { extraction_confidence: 0.95 } }),
)
if (fallbackConfidence !== 0.7) {
  throw new Error('Expected confidence_score fallback when overall_decision_confidence is absent.')
}

const syntheticItems = [
  makeItem({ item_id: '1', pipe_id: '1' }),
  makeItem({ item_id: '2', pipe_id: '2' }),
]
if (!shouldUseSyntheticRowRef(syntheticItems)) {
  throw new Error('Expected synthetic sequential refs to use Row column.')
}
if (resolveItemRefColumnHeader(syntheticItems) !== 'Row') {
  throw new Error('Expected synthetic refs to resolve Row column header.')
}
if (
  resolveItemRefCellValue(syntheticItems[0], 0, '1', null) !== formatSyntheticRowRef(0)
) {
  throw new Error('Expected synthetic cell value to show Row 1.')
}

const explicitItems = [
  makeItem({
    item_id: '1',
    pipe_id: '1',
    traceability_identifier_label: 'Test No. 12',
  }),
]
if (shouldUseSyntheticRowRef(explicitItems)) {
  throw new Error('Expected explicit source label to disable synthetic row refs.')
}

console.info('presentation-safety.test.ts passed')
