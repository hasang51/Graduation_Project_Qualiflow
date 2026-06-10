import {
  dedupeReasons,
  dedupeExactStrings,
  formatConfidenceBreakdownDisplay,
  formatSyntheticRowRef,
  getPresentationSpecificationCheckDisplay,
  hasNoReliableLineItems,
  isItemMechanicallyIncomplete,
  isMechanicalVerificationIncomplete,
  isUnsupportedGradeSpecReview,
  MECHANICAL_INCOMPLETE_REASON,
  resolveDecisionConfidence,
  resolveItemRefCellValue,
  resolveItemRefColumnHeader,
  shouldUseSyntheticRowRef,
  UNSUPPORTED_GRADE_SPEC_REASON,
} from './presentation-safety'
import { SIZE_WEIGHT_COLUMN_HEADER } from './presentation-labels'
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

if (!hasNoReliableLineItems(makeExtraction({ items: [], total_items_detected: 0, outcome: 'NOT_VALIDATED' }))) {
  throw new Error('Expected zero line items to count as no reliable line items.')
}

if (
  !hasNoReliableLineItems(
    makeExtraction({
      review_reasons: ['no_items_extracted'],
      outcome: 'NOT_VALIDATED',
    }),
  )
) {
  throw new Error('Expected no_items_extracted review reason to count as no reliable line items.')
}

if (hasNoReliableLineItems(makeExtraction())) {
  throw new Error('Expected extracted line items to pass reliability guard.')
}

if (dedupeExactStrings(['a', 'a', 'b']).join(',') !== 'a,b') {
  throw new Error('Expected dedupeExactStrings to preserve order and remove exact duplicates.')
}

const exactReasonDedupe = dedupeReasons([
  'missing_critical_field:grade',
  'missing_critical_field:grade',
])
if (exactReasonDedupe.length !== 1 || exactReasonDedupe[0] !== 'missing_critical_field:grade') {
  throw new Error('Expected exact duplicate review reason to be shown once.')
}

const confidenceReasonDedupe = dedupeReasons([
  'Overall confidence is below the automatic approval threshold',
  'overall confidence is below the automatic approval threshold.',
  'confidence_below_threshold',
])
if (
  confidenceReasonDedupe.length !== 1 ||
  confidenceReasonDedupe[0] !== 'Overall confidence is below the automatic approval threshold.'
) {
  throw new Error('Expected confidence threshold reason casing/punctuation variants to canonicalize once.')
}

const traceabilityReasonDedupe = dedupeReasons([
  'critical identifier confidence is low',
  'Critical identifiers could not be verified with sufficient confidence',
  'traceability_unverified',
  'low_identifier_confidence',
])
if (
  traceabilityReasonDedupe.length !== 1 ||
  traceabilityReasonDedupe[0] !==
    'Traceability identifier could not be verified with sufficient confidence.'
) {
  throw new Error('Expected traceability confidence reasons to canonicalize once.')
}

const unsupportedSpecReasonDedupe = dedupeReasons([
  'unsupported_spec_family',
  "Grade family 'B500B' is recognised but not covered by deterministic rules.",
  'recognized grade/spec is not covered',
])
if (
  unsupportedSpecReasonDedupe.length !== 1 ||
  unsupportedSpecReasonDedupe[0] !== UNSUPPORTED_GRADE_SPEC_REASON
) {
  throw new Error('Expected unsupported grade/spec reasons to canonicalize once.')
}

const combinedUnsupportedDedupe = dedupeReasons([
  'explicit_unmapped_grade',
  'Grade is explicitly stated but not mapped',
  'unresolved grade or spec',
  'unsupported_spec_family',
  'EXPLICIT_UNMAPPED_GRADE',
])
if (
  combinedUnsupportedDedupe.length !== 1 ||
  combinedUnsupportedDedupe[0] !== UNSUPPORTED_GRADE_SPEC_REASON
) {
  throw new Error('Expected all unsupported grade/spec variants to canonicalize once.')
}

const unsupportedSpecConfidence = formatConfidenceBreakdownDisplay(
  'validation_confidence',
  1,
  makeExtraction({ outcome: 'UNSUPPORTED_SPEC_FAMILY', needs_review: true }),
)
if (unsupportedSpecConfidence !== 'N/A — spec not covered') {
  throw new Error('Expected validation confidence N/A for unsupported spec family.')
}

const unsupportedSpecDisplay = getPresentationSpecificationCheckDisplay(
  makeExtraction({ outcome: 'EXPLICIT_UNMAPPED_GRADE', needs_review: true }),
)
if (unsupportedSpecDisplay.label !== 'Not automated' || unsupportedSpecDisplay.reason !== UNSUPPORTED_GRADE_SPEC_REASON) {
  throw new Error('Expected explicit unmapped grade to show Not automated with canonical reason.')
}

if (!isUnsupportedGradeSpecReview(makeExtraction({ outcome: 'UNRESOLVED_SPEC' }))) {
  throw new Error('Expected UNRESOLVED_SPEC outcome to count as unsupported grade/spec review.')
}

const visualAmbiguityReasonDedupe = dedupeReasons([
  'visual_ambiguity_detected_in_row',
  'visual ambiguity detected in row',
])
if (
  visualAmbiguityReasonDedupe.length !== 1 ||
  visualAmbiguityReasonDedupe[0] !== 'Visual ambiguity was detected in the extracted row.'
) {
  throw new Error('Expected visual ambiguity reasons to canonicalize once.')
}

const zeroItemConfidence = formatConfidenceBreakdownDisplay(
  'validation_confidence',
  1,
  makeExtraction({ items: [], total_items_detected: 0, outcome: 'NOT_VALIDATED' }),
)
if (zeroItemConfidence !== 'N/A — no line items') {
  throw new Error('Expected validation confidence to show N/A for zero line items.')
}

const decisionConfidenceDisplay = formatConfidenceBreakdownDisplay(
  'overall_decision_confidence',
  0.42,
  makeExtraction({ items: [], total_items_detected: 0, outcome: 'NOT_VALIDATED' }),
)
if (decisionConfidenceDisplay !== '42%') {
  throw new Error('Expected decision confidence to remain numeric for zero line items.')
}

if (SIZE_WEIGHT_COLUMN_HEADER !== 'Size / Weight') {
  throw new Error('Expected table size/weight header to use presentation-safe label.')
}

console.info('presentation-safety.test.ts passed')
