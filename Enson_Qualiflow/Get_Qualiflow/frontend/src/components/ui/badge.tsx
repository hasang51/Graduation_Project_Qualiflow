import { cn } from '../../lib/utils'
import type { ComplianceState } from '../../types/qualiflow'

interface BadgeProps {
  text: string
  tone?: 'neutral' | 'info' | 'danger' | 'success' | 'warning' | ComplianceState
}

const toneMap: Record<NonNullable<BadgeProps['tone']>, string> = {
  neutral: 'bg-slate-800 text-slate-200 border-slate-700',
  info: 'bg-sky-950/50 text-sky-300 border-sky-700/60',
  danger: 'bg-rose-950/40 text-rose-300 border-rose-700/60',
  success: 'bg-emerald-950/40 text-emerald-300 border-emerald-700/60',
  warning: 'bg-amber-950/40 text-amber-300 border-amber-700/60',
  compliant: 'bg-emerald-950/40 text-emerald-300 border-emerald-700/60',
  'non-compliant': 'bg-rose-950/40 text-rose-300 border-rose-700/60',
  'not-validated': 'bg-amber-950/40 text-amber-300 border-amber-700/60',
  'needs-review': 'bg-sky-950/50 text-sky-300 border-sky-700/60',
}

export function Badge({ text, tone = 'neutral' }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md border px-2.5 py-1 text-xs font-medium uppercase tracking-wide',
        toneMap[tone],
      )}
    >
      {text}
    </span>
  )
}
