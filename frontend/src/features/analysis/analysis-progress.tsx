import { LoaderCircle } from 'lucide-react'
import { Card } from '../../components/ui/card'

interface AnalysisProgressProps {
  currentStep: string
  active: boolean
}

const steps = [
  'Uploading PDF',
  'Processing pages',
  'Extracting structured data',
  'Validating compliance',
]

export function AnalysisProgress({ currentStep, active }: AnalysisProgressProps) {
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
        {steps.map((step) => (
          <div key={step} className="flex items-center gap-2 text-sm">
            <div
              className={`h-2 w-2 rounded-full ${active && step === currentStep ? 'bg-sky-400 shadow-[0_0_12px_rgba(56,189,248,0.7)]' : 'bg-slate-700'}`}
            />
            <span className={active && step === currentStep ? 'text-slate-100' : 'text-slate-500'}>{step}</span>
          </div>
        ))}
      </div>
    </Card>
  )
}
