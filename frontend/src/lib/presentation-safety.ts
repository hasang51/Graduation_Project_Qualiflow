import {
  getSpecificationCheckDisplay,
  type SpecificationCheckDisplay,
} from './format'
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
