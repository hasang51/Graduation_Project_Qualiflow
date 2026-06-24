import { Check, LoaderCircle } from 'lucide-react'
import { Card } from '../../components/ui/card'

interface AnalysisProgressProps {
  currentStepIndex: number
  active: boolean
  steps?: string[]
}

const defaultSteps = [
  'Uploading PDF',
  'Queued for processing',
  'Processing pages',
  'Extracting structured data',
  'Validating compliance',
]

function stepStatus(index: number, currentStepIndex: number, active: boolean): 'completed' | 'active' | 'pending' {
  if (!active) return 'pending'
  if (index < currentStepIndex) return 'completed'
  if (index === currentStepIndex) return 'active'
  return 'pending'
}

export function AnalysisProgress({ currentStepIndex, active, steps = defaultSteps }: AnalysisProgressProps) {
  const currentStep = steps[currentStepIndex] ?? steps[0]

  return (
    <Card className="space-y-5">
      <div className="flex items-center gap-3">
        <LoaderCircle className={`h-5 w-5 text-sky-400 ${active ? 'animate-spin' : ''}`} />
        <div>
          <p className="text-sm font-semibold text-slate-100">
            {active ? 'Document analysis in progress' : 'Ready for analysis'}
          </p>
          <p className="text-sm text-slate-400">{active ? currentStep : 'Upload a PDF and start extraction.'}</p>
        </div>
      </div>

      <div className="space-y-2">
        {steps.map((step, index) => {
          const status = stepStatus(index, currentStepIndex, active)
          return (
            <div key={step} className="flex items-center gap-2 text-sm">
              {status === 'completed' ? (
                <Check className="h-3.5 w-3.5 shrink-0 text-emerald-400" aria-hidden />
              ) : (
                <div
                  className={`h-2 w-2 shrink-0 rounded-full ${
                    status === 'active'
                      ? 'bg-sky-400 shadow-[0_0_12px_rgba(56,189,248,0.7)]'
                      : 'bg-slate-700'
                  }`}
                />
              )}
              <span
                className={
                  status === 'active'
                    ? 'text-slate-100'
                    : status === 'completed'
                      ? 'text-slate-400'
                      : 'text-slate-500'
                }
              >
                {step}
              </span>
            </div>
          )
        })}
      </div>

      {active && <p className="text-xs text-slate-500">Noisy scans may take up to a minute.</p>}
    </Card>
  )
}
