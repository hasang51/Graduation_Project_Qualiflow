import type { ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
}

const variants: Record<ButtonVariant, string> = {
  primary:
    'bg-sky-500 text-slate-950 shadow-lg shadow-sky-500/25 hover:bg-sky-400 disabled:bg-sky-700',
  secondary:
    'bg-slate-800 text-slate-100 hover:bg-slate-700 border border-slate-700',
  ghost:
    'bg-transparent text-slate-200 hover:bg-slate-800 border border-slate-700',
  danger:
    'bg-rose-500 text-white hover:bg-rose-400 border border-rose-400/20',
}

export function Button({ className, variant = 'primary', ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex h-10 items-center justify-center rounded-lg px-4 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60',
        variants[variant],
        className,
      )}
      {...props}
    />
  )
}
