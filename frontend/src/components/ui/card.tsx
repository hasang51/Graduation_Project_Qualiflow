import type { HTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'rounded-xl border border-slate-800 bg-slate-900/80 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] backdrop-blur',
        className,
      )}
      {...props}
    />
  )
}
