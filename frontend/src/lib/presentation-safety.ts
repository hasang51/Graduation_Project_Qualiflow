import {
  getSpecificationCheckDisplay,
  type SpecificationCheckDisplay,
} from './format'
import { formatReviewReason } from './review-reason-labels'
import type { ExtractedItem, ExtractionResponse } from '../types/qualiflow'

export const MECHANICAL_CRITICAL_REVIEW_REASONS = [
  'missing_critical_field:yield_strength',
  'missing_critical_field:tensile_strength',
  'missing_critical_field:elongation',
] as const

export const MECHANICAL_INCOMPLETE_REASON =
  'Mechanical verification is incomplete because required mechanical values are missing.'

const MECHANICAL_TEST_NUMBER_LABEL =
  /\b(test\s*no\.?|test\s*number|test\s*#|specimen|sample\s*no\.?|prüf|probe)\b/i

const MISSING_CANNOT_VERIFY_PATTERN = /missing\s*-\s*cannot verify/i

function hasMechanicalReviewReason(reviewReasons: string[] | undefined): boolean {
  if (!reviewReasons?.length) return false
  return MECHANICAL_CRITICAL_REVIEW_REASONS.some((reason) => reviewReasons.includes(reason))
}

function hasNullMechanicalField(item: ExtractedItem): boolean {
  const mechanical = item.mechanical_properties
  if (!mechanical) return true
  return (
    mechanical.yield_strength_mpa === null ||
    mechanical.tensile_strength_mpa === null ||
    mechanical.elongation_percentage === null
  )
}

function hasMissingCannotVerifyDeviation(item: ExtractedItem): boolean {
  return (item.validation?.deviations ?? []).some((deviation) =>
    MISSING_CANNOT_VERIFY_PATTERN.test(deviation),
  )
}

export function isMechanicalVerificationIncomplete(
  data: Pick<ExtractionResponse, 'items' | 'review_reasons'>,
): boolean {
  if (hasMechanicalReviewReason(data.review_reasons)) return true
  return data.items.some(
    (item) => hasNullMechanicalField(item) || hasMissingCannotVerifyDeviation(item),
  )
}

export function isItemMechanicallyIncomplete(
  item: ExtractedItem,
  reviewReasons?: string[],
): boolean {
  if (hasMechanicalReviewReason(reviewReasons)) return true
  return hasNullMechanicalField(item) || hasMissingCannotVerifyDeviation(item)
}

export function getPresentationSpecificationCheckDisplay(
  data: ExtractionResponse,
): SpecificationCheckDisplay {
  if (isMechanicalVerificationIncomplete(data)) {
    return {
      label: 'Incomplete',
      reason: MECHANICAL_INCOMPLETE_REASON,
      tone: 'not-validated',
    }
  }

  if (isUnsupportedGradeSpecReview(data)) {
    return {
      label: 'Not automated',
      reason: UNSUPPORTED_GRADE_SPEC_REASON,
      tone: 'not-validated',
    }
  }

  return getSpecificationCheckDisplay(data)
}

export function resolveDecisionConfidence(data: ExtractionResponse): number {
  const fromBreakdown = data.confidence_breakdown?.overall_decision_confidence
  if (typeof fromBreakdown === 'number') return fromBreakdown
  return data.confidence_score
}

export function resolveExtractionConfidence(data: ExtractionResponse): number | null {
  const fromBreakdown = data.confidence_breakdown?.extraction_confidence
  if (typeof fromBreakdown === 'number') return fromBreakdown
  return null
}

function isSequentialItemId(itemId: string, index: number): boolean {
  const normalized = itemId.trim()
  if (/^\d+$/.test(normalized)) {
    return Number(normalized) === index + 1
  }

  const match = normalized.toLowerCase().match(/^(?:item|row)[-_ ]?(\d+)$/)
  return match !== null && Number(match[1]) === index + 1
}

function hasExplicitSourceEvidence(
  item: ExtractedItem,
  explanation?: Record<string, unknown> | null,
): boolean {
  if (item.traceability_identifier_label?.trim()) return true

  const notes = (explanation?.evidence_propagation_notes as unknown[]) ?? []
  for (const note of notes) {
    if (!note || typeof note !== 'object') continue
    const record = note as Record<string, unknown>
    if (record.field !== 'item_id') continue
    const sourceText = String(record.source ?? record.reason ?? '').trim()
    if (sourceText) return true
  }

  return false
}

function isSyntheticSequentialRef(
  item: ExtractedItem,
  index: number,
  explanation?: Record<string, unknown> | null,
): boolean {
  if (hasExplicitSourceEvidence(item, explanation)) return false

  const itemId = item.item_id?.trim() ?? ''
  const pipeId = item.pipe_id?.trim() ?? ''

  if (itemId === '1' && pipeId === '1') return true

  if (itemId && isSequentialItemId(itemId, index)) return true

  return false
}

export function shouldUseSyntheticRowRef(
  items: ExtractedItem[],
  explanation?: Record<string, unknown> | null,
): boolean {
  if (items.length === 0) return false
  return items.every((item, index) => isSyntheticSequentialRef(item, index, explanation))
}

export function formatSyntheticRowRef(index: number): string {
  return `Row ${index + 1}`
}

export function resolveItemRefColumnHeader(
  items: ExtractedItem[],
  explanation?: Record<string, unknown> | null,
): string {
  const notes = (explanation?.evidence_propagation_notes as unknown[]) ?? []
  for (const note of notes) {
    if (!note || typeof note !== 'object') continue
    const record = note as Record<string, unknown>
    if (record.field !== 'item_id') continue
    const sourceText = String(record.source ?? record.reason ?? '')
    if (MECHANICAL_TEST_NUMBER_LABEL.test(sourceText)) return 'Test No.'
  }

  for (const item of items) {
    if (!item.item_id?.trim()) continue
    if (item.traceability_identifier_type === 'item_id') {
      const label = item.traceability_identifier_label ?? ''
      if (MECHANICAL_TEST_NUMBER_LABEL.test(label)) return 'Test No.'
    }
  }

  if (shouldUseSyntheticRowRef(items, explanation)) return 'Row'

  return 'Source Ref.'
}

export function resolveItemRefCellValue(
  item: ExtractedItem,
  index: number,
  renderedValue: string | null,
  explanation?: Record<string, unknown> | null,
  missingValue = '—',
): string {
  if (isSyntheticSequentialRef(item, index, explanation)) {
    return formatSyntheticRowRef(index)
  }
  if (renderedValue === null || renderedValue === undefined || renderedValue === missingValue) {
    return missingValue
  }
  return renderedValue
}

export const NO_RELIABLE_LINE_ITEM_REASONS = new Set([
  'no_items_extracted',
  'table_found_but_no_rows',
])

export function dedupeExactStrings(values: unknown[]): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  for (const value of values) {
    const text = String(value)
    if (seen.has(text)) continue
    seen.add(text)
    result.push(text)
  }
  return result
}

const TRACEABILITY_IDENTIFIER_CONFIDENCE_REASON =
  'Traceability identifier could not be verified with sufficient confidence.'
const OVERALL_CONFIDENCE_THRESHOLD_REASON =
  'Overall confidence is below the automatic approval threshold.'
export const UNSUPPORTED_GRADE_SPEC_REASON =
  'Recognized grade/spec is not covered by deterministic validation rules.'
export const UNSUPPORTED_GRADE_SPEC_DECISION_HELPER =
  'Final decision requires human review because the recognized grade/spec is not covered by deterministic validation rules.'
const VISUAL_AMBIGUITY_REASON =
  'Visual ambiguity was detected in the extracted row.'

const UNSUPPORTED_GRADE_SPEC_OUTCOMES = new Set([
  'EXPLICIT_UNMAPPED_GRADE',
  'UNSUPPORTED_SPEC_FAMILY',
  'UNRESOLVED_SPEC',
])

const UNSUPPORTED_GRADE_SPEC_TOKEN_KEYS = new Set([
  'explicit unmapped grade',
  'unsupported spec family',
  'unresolved spec',
  'unresolved grade or spec',
  'explicit unmapped grade',
  'specification family is not supported',
  'grade is explicitly stated but not mapped',
])

const CANONICAL_DISPLAY_REASONS = new Set([
  TRACEABILITY_IDENTIFIER_CONFIDENCE_REASON,
  OVERALL_CONFIDENCE_THRESHOLD_REASON,
  UNSUPPORTED_GRADE_SPEC_REASON,
  VISUAL_AMBIGUITY_REASON,
])

const SCAN_OCR_TABLE_UNCERTAINTY_TOKENS = new Set([
  'mechanical_table_alignment_uncertain',
  'visual_ambiguity_detected_in_row',
  'document readability concerns noted in analysis remarks',
  'low-confidence rows detected',
  'extraction structure is incomplete',
])

const TRACEABILITY_IDENTIFIER_REASON_KEYS = new Set([
  'critical identifier confidence is low',
  'critical identifiers could not be verified with sufficient confidence',
  'critical identifier unverified',
  'heat number is uncertain',
  'heat number uncertain',
  'low identifier confidence',
  'low confidence: heat number',
  'traceability critical identifiers could not be verified',
  'traceability identifier ocr uncertain',
  'traceability identifier requires ocr verification',
  'traceability identifiers require human verification',
  'traceability unverified',
  'weak heat number evidence',
])

const OVERALL_CONFIDENCE_REASON_KEYS = new Set([
  'confidence below threshold',
  'confidence falls below threshold',
  'overall confidence is below the automatic approval threshold',
])

const VISUAL_AMBIGUITY_REASON_KEYS = new Set([
  'visual ambiguity',
  'visual ambiguity detected in row',
  'visual ambiguity detected in the extracted row',
  'visual ambiguity was detected in the extracted row',
])

function normalizeReasonKey(reason: string): string {
  return reason
    .trim()
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/[.!?]+$/g, '')
    .toLowerCase()
}

function hasUnsupportedGradeSpecMeaning(keys: string[]): boolean {
  return keys.some((key) => {
    if (UNSUPPORTED_GRADE_SPEC_TOKEN_KEYS.has(key)) return true
    if (key === 'unsupported spec family') return true
    if (key === 'specification family is not supported') return true
    if (key.includes('unsupported spec family')) return true
    if (key.includes('recognized grade/spec is not covered')) return true
    if (key.includes('recognised grade/spec is not covered')) return true
    if (key.includes('grade/spec not covered')) return true
    if (key.includes('explicitly stated but not mapped')) return true
    if (key.includes('unresolved grade or spec')) return true

    const mentionsGradeOrSpec = /\b(grade|spec|specification|family)\b/.test(key)
    return mentionsGradeOrSpec && key.includes('not covered') && key.includes('deterministic')
  })
}

function collectReviewReasonStrings(data: ExtractionResponse): string[] {
  const reasons: string[] = [...(data.review_reasons ?? [])]
  const review = (data.explanation?.review_policy ?? {}) as Record<string, unknown>
  for (const bucket of ['review_reasons', 'structured_reasons', 'evidence_gaps', 'all_reasons']) {
    const values = review[bucket]
    if (Array.isArray(values)) {
      reasons.push(...values.map((value) => String(value)))
    }
  }
  for (const item of data.items) {
    for (const deviation of item.validation?.deviations ?? []) {
      reasons.push(deviation)
    }
  }
  return reasons
}

export function isUnsupportedGradeSpecReason(reason: string): boolean {
  const key = getReviewReasonDedupeKey(reason)
  return key === normalizeReasonKey(UNSUPPORTED_GRADE_SPEC_REASON)
}

export function isUnsupportedGradeSpecReview(data: ExtractionResponse): boolean {
  if (data.outcome && UNSUPPORTED_GRADE_SPEC_OUTCOMES.has(data.outcome)) {
    return true
  }

  if (
    data.items.some((item) => {
      const outcome = item.validation?.outcome
      return outcome !== null && outcome !== undefined && UNSUPPORTED_GRADE_SPEC_OUTCOMES.has(outcome)
    })
  ) {
    return true
  }

  return collectReviewReasonStrings(data).some(isUnsupportedGradeSpecReason)
}

export function hasScanOcrTableUncertainty(data: ExtractionResponse): boolean {
  const reasons = collectReviewReasonStrings(data)
  return reasons.some((reason) => {
    const trimmed = reason.trim().toLowerCase()
    if (SCAN_OCR_TABLE_UNCERTAINTY_TOKENS.has(trimmed)) return true
    if (SCAN_OCR_TABLE_UNCERTAINTY_TOKENS.has(reason.trim())) return true
    const key = normalizeReasonKey(reason)
    return (
      key.includes('visual ambiguity') ||
      key.includes('table alignment') ||
      key.includes('ocr') ||
      key.includes('readability')
    )
  })
}

export function formatDisplayReviewReason(reason: string): string {
  const normalized = normalizeReviewReason(reason)
  if (!normalized) return ''

  if (CANONICAL_DISPLAY_REASONS.has(normalized)) {
    return normalized
  }

  if (hasUnsupportedGradeSpecMeaning([normalizeReasonKey(normalized)])) {
    return UNSUPPORTED_GRADE_SPEC_REASON
  }

  return formatReviewReason(normalized)
}

export function formatValidationOutcome(outcome: string | null | undefined): string {
  if (!outcome) return 'NOT_VALIDATED'
  if (UNSUPPORTED_GRADE_SPEC_OUTCOMES.has(outcome)) {
    return UNSUPPORTED_GRADE_SPEC_REASON
  }
  return outcome.replace(/_/g, ' ')
}

export function normalizeReviewReason(reason: string): string {
  const trimmed = reason.trim()
  if (!trimmed) return ''

  const formatted = formatReviewReason(trimmed).trim()
  const keys = [trimmed, formatted].map(normalizeReasonKey)

  if (keys.some((key) => TRACEABILITY_IDENTIFIER_REASON_KEYS.has(key))) {
    return TRACEABILITY_IDENTIFIER_CONFIDENCE_REASON
  }

  if (keys.some((key) => OVERALL_CONFIDENCE_REASON_KEYS.has(key))) {
    return OVERALL_CONFIDENCE_THRESHOLD_REASON
  }

  if (hasUnsupportedGradeSpecMeaning(keys)) {
    return UNSUPPORTED_GRADE_SPEC_REASON
  }

  if (keys.some((key) => VISUAL_AMBIGUITY_REASON_KEYS.has(key))) {
    return VISUAL_AMBIGUITY_REASON
  }

  return trimmed
}

export function getReviewReasonDedupeKey(reason: string): string {
  return normalizeReasonKey(normalizeReviewReason(reason))
}

export function dedupeReasons(reasons: string[]): string[] {
  const seen = new Set<string>()
  const result: string[] = []

  for (const reason of reasons) {
    const normalized = normalizeReviewReason(reason)
    if (!normalized) continue

    const key = normalizeReasonKey(normalized)
    if (seen.has(key)) continue

    seen.add(key)
    result.push(normalized)
  }

  return result
}

export function hasNoReliableLineItems(
  data: Pick<ExtractionResponse, 'items' | 'review_reasons' | 'outcome' | 'total_items_detected'>,
): boolean {
  if (data.items.length === 0) return true
  if (data.total_items_detected === 0) return true
  const reasons = data.review_reasons ?? []
  return reasons.some((reason) => NO_RELIABLE_LINE_ITEM_REASONS.has(reason))
}

const CONFIDENCE_NA_KEYS = new Set(['spec_resolution_confidence', 'validation_confidence'])

export function formatConfidenceBreakdownDisplay(
  key: string,
  value: number,
  data: ExtractionResponse,
): string {
  if (hasNoReliableLineItems(data) && CONFIDENCE_NA_KEYS.has(key)) {
    return 'N/A — no line items'
  }
  if (key === 'validation_confidence' && isUnsupportedGradeSpecReview(data)) {
    return 'N/A — spec not covered'
  }
  return `${Math.round(Number(value) * 100)}%`
}

export const VALIDATION_NOT_PERFORMED_MESSAGE =
  'No rule-based validation was performed because no reliable line items were extracted.'

const CONFIDENCE_REVIEW_HELPER_TEXT =
  'Final confidence is reduced because the scan contains OCR, header, or table-alignment uncertainty.'

export function getPresentationConfidenceHelperText(
  data: ExtractionResponse,
  threshold = 0.75,
): string | null {
  if (isUnsupportedGradeSpecReview(data)) {
    return UNSUPPORTED_GRADE_SPEC_DECISION_HELPER
  }

  if (data.needs_review === true && hasScanOcrTableUncertainty(data)) {
    return CONFIDENCE_REVIEW_HELPER_TEXT
  }

  if (data.needs_review === true) {
    return CONFIDENCE_REVIEW_HELPER_TEXT
  }

  if (data.needs_review === false && data.confidence_score < threshold) {
    return 'Low overall confidence did not block auto-accept because required fields passed deterministic validation.'
  }

  return null
}

export function getCompliantNeedsReviewNote(data: ExtractionResponse): string {
  if (isUnsupportedGradeSpecReview(data)) {
    return UNSUPPORTED_GRADE_SPEC_DECISION_HELPER
  }
  if (hasScanOcrTableUncertainty(data)) {
    return 'Values appear compliant, but human review is required due to OCR or table-alignment uncertainty.'
  }
  return 'Values appear compliant, but human review is required before automatic approval.'
}

export function getNoDeviationsMessage(data: ExtractionResponse): string {
  if (hasNoReliableLineItems(data)) {
    return VALIDATION_NOT_PERFORMED_MESSAGE
  }
  const isCompliant =
    data.outcome === 'COMPLIANT' || data.is_compliant === true
  const needsReview = data.needs_review === true
  if (isCompliant && needsReview) {
    if (isUnsupportedGradeSpecReview(data)) {
      return `No threshold deviations detected. ${UNSUPPORTED_GRADE_SPEC_DECISION_HELPER}`
    }
    if (hasScanOcrTableUncertainty(data)) {
      return 'No threshold deviations detected. Human review is required due to OCR or table-alignment uncertainty.'
    }
    return 'No threshold deviations detected. Human review is required before automatic approval.'
  }
  return 'No deviations detected.'
}
