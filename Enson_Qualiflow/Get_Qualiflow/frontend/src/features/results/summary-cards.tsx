import { Badge } from '../../components/ui/badge'
import { Card } from '../../components/ui/card'
import { formatConfidence, formatNullable, getComplianceStateFromOutcome } from '../../lib/format'
import type { ExtractionResponse, TraceabilityStatus } from '../../types/qualiflow'

interface SummaryCardsProps {
  data: ExtractionResponse
}

function confidenceTone(score: number): 'success' | 'warning' | 'danger' {
  if (score >= 0.85) return 'success'
  if (score >= 0.6) return 'warning'
  return 'danger'
}

function complianceLabel(
  outcome: string | null | undefined,
  isCompliant: boolean | null,
  needsReview: boolean,
  traceabilityStatus?: TraceabilityStatus | null,
) {
  if ((outcome === 'COMPLIANT' || isCompliant === true) && traceabilityStatus !== 'VERIFIED') return 'Needs review'
  if (needsReview) return 'Needs review'
  if (outcome === 'COMPLIANT') return 'Compliant'
  if (outcome === 'NON_COMPLIANT') return 'Non-compliant'
  if (outcome === 'UNRESOLVED_SPEC') return 'Spec unresolved'
  if (outcome === 'UNSUPPORTED_SPEC_FAMILY') return 'Unsupported spec family'
  if (outcome === 'NEEDS_REVIEW') return 'Needs review'
  if (outcome === 'NOT_VALIDATED') return 'Not validated'
  if (isCompliant === true) return 'Compliant'
  if (isCompliant === false) return 'Non-compliant'
  return 'Not validated'
}

export function SummaryCards({ data }: SummaryCardsProps) {
  const needsReview = data.needs_review === true || data.status === 'NEEDS_REVIEW'
  const complianceState = getComplianceStateFromOutcome(
    data.outcome,
    data.is_compliant,
    needsReview,
    data.traceability_status,
  )
  const traceabilityBlocksCompliance =
    data.traceability_status !== 'VERIFIED' && data.review_reasons?.includes('traceability_unverified')

  const cards = [
    { label: 'Supplier Name', value: formatNullable(data.supplier_name, 'Unknown') },
    { label: 'Document Type', value: formatNullable(data.document_type, 'Unknown') },
    { label: 'Certificate Date', value: formatNullable(data.certificate_date) },
    { label: 'Total Items Detected', value: String(data.total_items_detected) },
    {
      label: 'Confidence Score',
      value: <Badge text={formatConfidence(data.confidence_score)} tone={confidenceTone(data.confidence_score)} />,
    },
    {
      label: 'Compliance Status',
      value: (
        <Badge
          text={complianceLabel(data.outcome, data.is_compliant, needsReview, data.traceability_status)}
          tone={complianceState}
        />
      ),
    },
  ]

  return (
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {cards.map((card) => (
        <Card key={card.label} className="space-y-2">
          <p className="text-xs uppercase tracking-wider text-slate-400">{card.label}</p>
          <div className="text-base font-semibold text-slate-100">{card.value}</div>
        </Card>
      ))}
      {traceabilityBlocksCompliance && (
        <Card className="space-y-2 md:col-span-2 xl:col-span-3">
          <Badge
            text="Mechanical compliance passed, but traceability identifiers require human verification."
            tone="warning"
          />
        </Card>
      )}
    </section>
  )
}
