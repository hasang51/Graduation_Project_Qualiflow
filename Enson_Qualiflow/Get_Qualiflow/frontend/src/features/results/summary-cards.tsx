import { Badge } from '../../components/ui/badge'
import { Card } from '../../components/ui/card'
import { formatConfidence, formatNullable, getComplianceState } from '../../lib/format'
import type { ExtractionResponse } from '../../types/qualiflow'

interface SummaryCardsProps {
  data: ExtractionResponse
}

function confidenceTone(score: number): 'success' | 'warning' | 'danger' {
  if (score >= 0.85) return 'success'
  if (score >= 0.6) return 'warning'
  return 'danger'
}

function complianceLabel(isCompliant: boolean | null) {
  if (isCompliant === true) return 'Compliant'
  if (isCompliant === false) return 'Non-compliant'
  return 'Not validated'
}

export function SummaryCards({ data }: SummaryCardsProps) {
  const complianceState = getComplianceState(data.is_compliant)

  const cards = [
    { label: 'Supplier Name', value: formatNullable(data.supplier_name, 'Unknown') },
    { label: 'Document Type', value: formatNullable(data.document_type, 'Unknown') },
    { label: 'Certificate Date', value: formatNullable(data.certificate_date) },
    { label: 'Total Items Detected', value: String(data.total_items_detected) },
    {
      label: 'Confidence Score',
      value: <Badge text={formatConfidence(data.confidence_score)} tone={confidenceTone(data.confidence_score)} />,
    },
    { label: 'Compliance Status', value: <Badge text={complianceLabel(data.is_compliant)} tone={complianceState} /> },
  ]

  return (
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {cards.map((card) => (
        <Card key={card.label} className="space-y-2">
          <p className="text-xs uppercase tracking-wider text-slate-400">{card.label}</p>
          <div className="text-base font-semibold text-slate-100">{card.value}</div>
        </Card>
      ))}
    </section>
  )
}
