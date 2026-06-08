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

export const DEFAULT_REVIEW_CONFIDENCE_THRESHOLD = 0.75

export function formatConfidence(score: number): string {
  const clamped = Math.max(0, Math.min(score, 1))
  return `${Math.round(clamped * 100)}%`
}

export function getConfidenceHelperText(
  data: {
    confidence_score: number
    needs_review?: boolean
    review_reasons?: string[]
  },
  threshold = DEFAULT_REVIEW_CONFIDENCE_THRESHOLD,
): string | null {
  if (data.needs_review === true) {
    const reasons = (data.review_reasons ?? []).filter(Boolean)
    return reasons.length > 0 ? reasons.join('; ') : 'Review required.'
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
