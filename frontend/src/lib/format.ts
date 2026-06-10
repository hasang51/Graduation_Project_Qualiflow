import type { ComplianceState, TraceabilityStatus, ValidationOutcome } from '../types/qualiflow'

export const NA_VALUE = 'N/A'
export const MISSING_VALUE = '—'

export function formatNullable(
  value: string | number | null | undefined,
  fallback = MISSING_VALUE,
): string {
  if (value === null || value === undefined || value === '') {
    return fallback
  }
  return String(value)
}

export function formatNumber(
  value: number | null | undefined,
  options?: Intl.NumberFormatOptions,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return MISSING_VALUE
  }

  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 2,
    ...options,
  }).format(value)
}

const PLAUSIBLE_MPA_MIN = 100
const PLAUSIBLE_MPA_MAX = 2500

function looksLikeThousandsGroupedMpa(value: number): number | null {
  if (!(value > 0 && value < 50)) return null

  const promoted = Math.round(value * 1000)
  if (promoted < PLAUSIBLE_MPA_MIN || promoted > PLAUSIBLE_MPA_MAX) {
    return null
  }

  const fractionalDigits = value.toFixed(4).split('.')[1] ?? ''
  const hasThreeDigitFraction = fractionalDigits.replace(/0+$/, '').length === 3
  const likelyDecimalMpa = value <= 10 && fractionalDigits.length > 0 && !hasThreeDigitFraction

  if (likelyDecimalMpa && promoted > 500) {
    return null
  }

  if (hasThreeDigitFraction) {
    return promoted
  }

  return null
}

export function formatMpaDisplay(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return MISSING_VALUE
  }

  const promoted = looksLikeThousandsGroupedMpa(value)
  if (promoted !== null) {
    return String(promoted)
  }

  if (Number.isInteger(value) || Math.abs(value - Math.round(value)) < 1e-6) {
    return String(Math.round(value))
  }

  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value)
}

export const DEFAULT_REVIEW_CONFIDENCE_THRESHOLD = 0.75

export function formatConfidence(score: number): string {
  const clamped = Math.max(0, Math.min(score, 1))
  return `${Math.round(clamped * 100)}%`
}

export const EXTRACTION_CONFIDENCE_CAPTION =
  'Reflects extraction and routing certainty, not automatic compliance approval.'

const CONFIDENCE_REVIEW_HELPER_TEXT =
  'Final confidence is reduced because the scan contains OCR, header, or table-alignment uncertainty.'

export const LOW_SPEC_RESOLUTION_CONFIDENCE_THRESHOLD = 0.35

export function resolveSpecResolutionConfidence(data: {
  confidence_breakdown?: Record<string, number> | null
  explanation?: Record<string, unknown> | null
}): number | null {
  const direct = data.confidence_breakdown?.spec_resolution_confidence
  if (typeof direct === 'number') return direct

  const explanation = data.explanation ?? {}
  const nested = explanation.confidence_breakdown
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    const value = (nested as Record<string, number>).spec_resolution_confidence
    if (typeof value === 'number') return value
  }

  return null
}

export type SpecificationCheckDisplay = {
  label: string
  reason?: string
  tone: ComplianceState | 'needs-review'
}

export function getSpecificationCheckDisplay(data: {
  outcome?: ValidationOutcome | null
  is_compliant?: boolean | null
  compliance_status?: string | null
  confidence_breakdown?: Record<string, number> | null
  explanation?: Record<string, unknown> | null
}): SpecificationCheckDisplay {
  const baseLabel = getSpecificationCheckLabel(data)
  const specResolutionConfidence = resolveSpecResolutionConfidence(data)

  if (
    baseLabel === 'Unknown' &&
    specResolutionConfidence !== null &&
    specResolutionConfidence < LOW_SPEC_RESOLUTION_CONFIDENCE_THRESHOLD
  ) {
    return {
      label: 'Not automated',
      reason: 'Recognized grade/spec is not covered by deterministic validation rules.',
      tone: 'not-validated',
    }
  }

  return {
    label: baseLabel,
    tone: getSpecificationCheckTone(baseLabel),
  }
}

export function getConfidenceHelperText(
  data: {
    confidence_score: number
    needs_review?: boolean
  },
  threshold = DEFAULT_REVIEW_CONFIDENCE_THRESHOLD,
): string | null {
  if (data.needs_review === true) {
    return CONFIDENCE_REVIEW_HELPER_TEXT
  }

  if (data.needs_review === false && data.confidence_score < threshold) {
    return 'Low overall confidence did not block auto-accept because required fields passed deterministic validation.'
  }

  return null
}

export function getComplianceState(isCompliant: boolean | null): ComplianceState {
  if (isCompliant === true) return 'compliant'
  if (isCompliant === false) return 'non-compliant'
  return 'not-validated'
}

export type DetailComplianceLabel = 'COMPLIANT' | 'NEEDS REVIEW'
export type ProcessingDecisionLabel = 'AUTO_ACCEPT' | 'NEEDS_REVIEW'

export function normalizeDecisionToken(value: string | null | undefined): string {
  return (value ?? '').trim().toLowerCase().replace(/-/g, '_')
}

export function formatDecisionLabel(value: string | null | undefined): string {
  switch (normalizeDecisionToken(value)) {
    case 'auto_accept':
      return 'Auto-accept'
    case 'needs_review':
      return 'Needs review'
    case 'manual_review':
      return 'Manual review'
    default:
      return value?.trim() || 'Unknown'
  }
}

export function resolveProcessingDecisionValue(data: {
  processing_decision?: string | null
  needs_review?: boolean
}): string {
  const explicit = normalizeDecisionToken(data.processing_decision)
  if (explicit === 'auto_accept' || explicit === 'needs_review' || explicit === 'manual_review') {
    return explicit
  }
  return data.needs_review ? 'needs_review' : 'auto_accept'
}

function normalizeComplianceToken(value: string | null | undefined): string {
  return (value ?? '').trim().toUpperCase().replace(/\s+/g, '_')
}

export function getDetailComplianceLabel(data: {
  compliance_status?: string | null
  status?: string | null
  needs_review?: boolean
}): DetailComplianceLabel {
  const complianceStatus = normalizeComplianceToken(data.compliance_status)
  if (complianceStatus === 'COMPLIANT') return 'COMPLIANT'
  if (complianceStatus === 'NEEDS_REVIEW') return 'NEEDS REVIEW'

  const status = normalizeComplianceToken(data.status)
  if (status === 'NEEDS_REVIEW') return 'NEEDS REVIEW'
  if (status === 'AUTO_ACCEPT') return 'COMPLIANT'

  if (data.needs_review === true) return 'NEEDS REVIEW'
  if (data.needs_review === false) return 'COMPLIANT'

  if (status === 'COMPLETED') {
    return data.needs_review ? 'NEEDS REVIEW' : 'COMPLIANT'
  }

  return 'NEEDS REVIEW'
}

export function getProcessingDecision(needsReview: boolean | undefined): ProcessingDecisionLabel {
  return needsReview ? 'NEEDS_REVIEW' : 'AUTO_ACCEPT'
}

export type SpecificationCheckLabel = 'Compliant' | 'Non-compliant' | 'Unknown'
export type RoutingDecisionDisplayLabel =
  | 'Needs human review'
  | 'Auto-approved'
  | 'Rejected'
  | 'Unknown'

export function getSpecificationCheckLabel(data: {
  outcome?: ValidationOutcome | null
  is_compliant?: boolean | null
  compliance_status?: string | null
}): SpecificationCheckLabel {
  const outcome = data.outcome ?? null
  if (outcome === 'COMPLIANT') return 'Compliant'
  if (outcome === 'NON_COMPLIANT') return 'Non-compliant'

  const complianceStatus = normalizeComplianceToken(data.compliance_status)
  if (complianceStatus === 'COMPLIANT') return 'Compliant'
  if (complianceStatus === 'NON_COMPLIANT') return 'Non-compliant'

  if (data.is_compliant === true) return 'Compliant'
  if (data.is_compliant === false) return 'Non-compliant'

  return 'Unknown'
}

export function getRoutingDecisionLabel(data: {
  needs_review?: boolean
  processing_decision?: string | null
  status?: string | null
}): RoutingDecisionDisplayLabel {
  const decision = normalizeDecisionToken(data.processing_decision)
  const status = normalizeDecisionToken(data.status)

  if (decision === 'reject' || decision === 'rejected' || status === 'failed' || status === 'rejected') {
    return 'Rejected'
  }

  if (
    data.needs_review === true ||
    decision === 'needs_review' ||
    decision === 'manual_review' ||
    status === 'needs_review'
  ) {
    return 'Needs human review'
  }

  if (
    data.needs_review === false ||
    decision === 'auto_accept' ||
    status === 'auto_accept' ||
    status === 'completed'
  ) {
    return 'Auto-approved'
  }

  return 'Unknown'
}

export function getSpecificationCheckTone(
  label: SpecificationCheckLabel,
): ComplianceState | 'needs-review' {
  if (label === 'Compliant') return 'compliant'
  if (label === 'Non-compliant') return 'non-compliant'
  return 'not-validated'
}

export function getRoutingDecisionDisplayTone(
  label: RoutingDecisionDisplayLabel,
): 'success' | 'warning' | 'danger' | 'info' {
  if (label === 'Auto-approved') return 'success'
  if (label === 'Needs human review') return 'warning'
  if (label === 'Rejected') return 'danger'
  return 'info'
}

export function getDetailComplianceTone(label: DetailComplianceLabel): ComplianceState {
  return label === 'COMPLIANT' ? 'compliant' : 'needs-review'
}

export function getProcessingDecisionTone(decision: string): 'success' | 'warning' {
  return normalizeDecisionToken(decision) === 'auto_accept' ? 'success' : 'warning'
}

export function getComplianceStateFromOutcome(
  outcome: ValidationOutcome | null | undefined,
  isCompliant: boolean | null,
  needsReview = false,
  traceabilityStatus?: TraceabilityStatus | null,
): ComplianceState {
  if ((outcome === 'COMPLIANT' || isCompliant === true) && traceabilityStatus !== 'VERIFIED') return 'needs-review'
  if (needsReview) return 'needs-review'

  switch (outcome) {
    case 'COMPLIANT':
      return 'compliant'
    case 'NON_COMPLIANT':
      return 'non-compliant'
    case 'UNRESOLVED_SPEC':
    case 'UNSUPPORTED_SPEC_FAMILY':
    case 'EXPLICIT_UNMAPPED_GRADE':
    case 'MISSING_CRITICAL_FIELD_GRADE':
    case 'NEEDS_REVIEW':
      return 'needs-review'
    case 'NOT_VALIDATED':
      return 'not-validated'
    default:
      return getComplianceState(isCompliant)
  }
}

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** exponent
  return `${value.toFixed(value >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`
}
