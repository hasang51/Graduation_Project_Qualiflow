import { Card } from '../../components/ui/card'
import type { ExtractionResponse } from '../../types/qualiflow'

interface ExplanationPanelProps {
  data: ExtractionResponse
}

function renderList(values: unknown[] | undefined, empty: string) {
  if (!values || values.length === 0) {
    return <p className="text-sm text-slate-400">{empty}</p>
  }
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm text-slate-200">
      {values.map((value, idx) => (
        <li key={idx}>{String(value)}</li>
      ))}
    </ul>
  )
}

export function ExplanationPanel({ data }: ExplanationPanelProps) {
  const explanation = data.explanation ?? {}
  const profile = (explanation.document_profile ?? {}) as Record<string, unknown>
  const route = (explanation.route_decision ?? {}) as Record<string, unknown>
  const review = (explanation.review_policy ?? {}) as Record<string, unknown>
  const confidence = data.confidence_breakdown ?? ((explanation.confidence_breakdown ?? {}) as Record<string, number>)

  return (
    <section className="grid gap-4 xl:grid-cols-2">
      <Card className="space-y-2">
        <p className="text-xs uppercase tracking-wider text-slate-400">Document Profile</p>
        <p className="text-sm text-slate-200">Profile: {String(profile.quality_class ?? 'Unknown')}</p>
        <p className="text-sm text-slate-300">Reasons: {String((profile.reasons as string[] | undefined)?.join(', ') ?? '—')}</p>
      </Card>

      <Card className="space-y-2">
        <p className="text-xs uppercase tracking-wider text-slate-400">Route Decision</p>
        <p className="text-sm text-slate-200">Selected: {String(route.selected_route ?? '—')}</p>
        <p className="text-sm text-slate-200">Runtime route: {String(route.runtime_route ?? '—')}</p>
        <p className="text-sm text-slate-300">Strategy: {String(route.expected_strategy ?? '—')}</p>
      </Card>

      <Card className="space-y-2">
        <p className="text-xs uppercase tracking-wider text-slate-400">Validation Outcome</p>
        <p className="text-sm text-slate-200">Outcome: {String(data.outcome ?? 'NOT_VALIDATED')}</p>
        {renderList(data.review_reasons, 'No review reasons recorded.')}
      </Card>

      <Card className="space-y-2">
        <p className="text-xs uppercase tracking-wider text-slate-400">Review Reasons</p>
        {renderList(review.review_reasons as unknown[] | undefined, 'No structured review reasons.')}
        <p className="text-xs uppercase tracking-wider text-slate-500">Evidence Gaps</p>
        {renderList(review.evidence_gaps as unknown[] | undefined, 'No major evidence gaps flagged.')}
      </Card>

      <Card className="space-y-2">
        <p className="text-xs uppercase tracking-wider text-slate-400">Evidence / Propagation Notes</p>
        {renderList(
          (explanation.evidence_propagation_notes as unknown[] | undefined)?.map((v) => JSON.stringify(v)),
          'No propagated fields or conflicts.',
        )}
      </Card>

      <Card className="space-y-2">
        <p className="text-xs uppercase tracking-wider text-slate-400">Confidence Breakdown</p>
        {confidence && Object.keys(confidence).length > 0 ? (
          <ul className="space-y-1 text-sm text-slate-200">
            {Object.entries(confidence).map(([key, value]) => (
              <li key={key} className="flex justify-between">
                <span>{key}</span>
                <span>{Math.round(Number(value) * 100)}%</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-400">No confidence breakdown available.</p>
        )}
      </Card>
    </section>
  )
}
