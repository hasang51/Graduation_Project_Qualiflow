import type { ComplianceState } from '../types/qualiflow'

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

export function formatConfidence(score: number): string {
  const clamped = Math.max(0, Math.min(score, 1))
  return `${Math.round(clamped * 100)}%`
}

export function getComplianceState(isCompliant: boolean | null): ComplianceState {
  if (isCompliant === true) return 'compliant'
  if (isCompliant === false) return 'non-compliant'
  return 'not-validated'
}

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** exponent
  return `${value.toFixed(value >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`
}
