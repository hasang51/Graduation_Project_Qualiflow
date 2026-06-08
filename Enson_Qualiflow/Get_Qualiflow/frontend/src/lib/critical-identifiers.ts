import type { ExtractedItem } from '../types/qualiflow'

const IDENTIFIER_BLOCKING_REASONS = new Set([
  'critical_identifier_unverified',
  'identifier_occluded',
  'low_identifier_legibility',
  'ambiguous_identifier',
  'ocr_corruption_affecting_identifier',
  'partial_digit_visibility',
  'identifier_specific_confidence_failure',
  'visual ambiguity detected in row',
])

function normalizeReason(value: unknown): string {
  return String(value ?? '').trim().toLowerCase()
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function collectReasons(item: Record<string, unknown>): string[] {
  const buckets = [item.review_reasons, item.validation_reasons, item.evidence_gaps]
  const reasons: string[] = []
  for (const bucket of buckets) {
    if (Array.isArray(bucket)) {
      for (const reason of bucket) reasons.push(normalizeReason(reason))
    } else if (typeof bucket === 'string') {
      reasons.push(normalizeReason(bucket))
    }
  }
  return reasons
}

function fieldAliases(field: string): string[] {
  const aliases: Record<string, string[]> = {
    heat_number: ['heat_number', 'heat_no', 'heat no', 'heat'],
    heat_no: ['heat_number', 'heat_no', 'heat no', 'heat'],
    batch_number: ['batch_number', 'batch_no', 'batch no', 'batch'],
    item_id: ['item_id', 'pipe_id', 'item', 'pipe_coil_id', 'coil', 'pipe'],
    pipe_id: ['pipe_id', 'item_id', 'item', 'pipe_coil_id', 'coil', 'pipe'],
    pipe_coil_id: ['item_id', 'pipe_id', 'item', 'pipe_coil_id', 'coil', 'pipe'],
    certificate_number: ['certificate_number', 'certificate', 'cert'],
    order_number: ['order_number', 'order', 'po'],
  }
  return aliases[field] ?? [field]
}

function hasIdentifierBlockingReason(
  reasons: string[],
  fields: string[],
): boolean {
  return reasons.some((reason) => {
    if (IDENTIFIER_BLOCKING_REASONS.has(reason)) return true
    if (reason.includes('identifier') && (reason.includes('confidence') || reason.includes('weak') || reason.includes('ocr') || reason.includes('partial'))) {
      return true
    }
    if (!reason.includes('identifier') && !reason.includes('heat') && !reason.includes('batch') && !reason.includes('item') && !reason.includes('certificate') && !reason.includes('order')) {
      return false
    }
    const hasFieldAlias = fields.some((field) =>
      fieldAliases(field).some((alias) => reason.includes(alias)),
    )
    if (!hasFieldAlias) return false
    return (
      reason.includes('ambiguous') ||
      reason.includes('occluded') ||
      reason.includes('legibility') ||
      reason.includes('unverified') ||
      reason.includes('confidence') ||
      reason.includes('corrupt') ||
      reason.includes('partial')
    )
  })
}

type AcceptedLogicalPick =
  | { kind: 'absent' }
  | { kind: 'empty' }
  | { kind: 'value'; value: string }

/** First explicit ``accepted`` alias for logical field: absent, suppressed empty, or value. */
function pickAcceptedLogical(accepted: Record<string, unknown>, logicalField: string): AcceptedLogicalPick {
  for (const alias of fieldAliases(logicalField)) {
    if (!Object.prototype.hasOwnProperty.call(accepted, alias)) continue
    const value = accepted[alias]
    if (value === null || value === undefined || value === '' || value === '-') {
      return { kind: 'empty' }
    }
    return { kind: 'value', value: String(value) }
  }
  return { kind: 'absent' }
}

/** First non-empty raw value among logical field aliases on the row object. */
function readRawField(rawItem: Record<string, unknown>, logicalField: string): unknown {
  for (const alias of fieldAliases(logicalField)) {
    const value = rawItem[alias]
    if (value !== null && value !== undefined && value !== '' && value !== '-') {
      return value
    }
  }
  return undefined
}

export type RenderCriticalIdentifierOptions = {
  /**
   * When true (default), prefer ``traceability_identifier_value`` /
   * document-level consolidated trace IDs before iterating field-specific keys.
   * Disable for columns that must show only that semantic (e.g. Item ID vs Heat).
   */
  allowTraceabilityShortcut?: boolean
  /**
   * When true (default), after trying ``fields``, fall back through heat_number,
   * batch_number, etc. Disable for columns that must not borrow another column's display.
   */
  allowCrossFieldFallback?: boolean
}

export function renderCriticalIdentifier(
  item: ExtractedItem | Record<string, unknown>,
  fields: string[],
  missingValue = '—',
  opts?: RenderCriticalIdentifierOptions,
): string {
  const rawItem = asRecord(item) ?? {}
  const allowTraceabilityShortcut = opts?.allowTraceabilityShortcut !== false
  const allowCrossFieldFallback = opts?.allowCrossFieldFallback !== false
  const accepted =
    asRecord(rawItem.accepted_identifier_values) ??
    asRecord(rawItem.acceptedIdentifierValues)

  if (allowTraceabilityShortcut && accepted && Object.prototype.hasOwnProperty.call(accepted, 'traceability_identifier_value')) {
    const value = accepted.traceability_identifier_value
    if (value === null || value === undefined || value === '' || value === '-') {
      return missingValue
    }
    return String(value)
  }

  const topTraceabilityValue = rawItem.traceability_identifier_value
  if (
    allowTraceabilityShortcut &&
    topTraceabilityValue !== null &&
    topTraceabilityValue !== undefined &&
    topTraceabilityValue !== '' &&
    topTraceabilityValue !== '-'
  ) {
    return String(topTraceabilityValue)
  }

  const fallbackFields = allowCrossFieldFallback
    ? [
        ...fields,
        'heat_number',
        'batch_number',
        'colata_number',
        'lot_number',
        'cast_number',
        'charge_number',
      ]
    : [...fields]

  if (accepted) {
    let sawExplicitEmptyFromAccepted = false
    for (const field of fallbackFields) {
      const picked = pickAcceptedLogical(accepted, field)
      if (picked.kind === 'absent') continue
      if (picked.kind === 'empty') {
        sawExplicitEmptyFromAccepted = true
        continue
      }
      return picked.value
    }
    if (sawExplicitEmptyFromAccepted && !allowCrossFieldFallback) {
      return missingValue
    }
  }

  if (rawItem.identifier_visibility_verified === true) {
    for (const field of fallbackFields) {
      const value = readRawField(rawItem, field)
      if (value !== undefined) {
        return String(value)
      }
    }
    return missingValue
  }

  const reasons = collectReasons(rawItem)
  if (hasIdentifierBlockingReason(reasons, fallbackFields)) return missingValue

  if (rawItem.identifier_visibility_verified === false) return missingValue

  for (const field of fallbackFields) {
    const value = readRawField(rawItem, field)
    if (value !== undefined) {
      return String(value)
    }
  }
  return missingValue
}
