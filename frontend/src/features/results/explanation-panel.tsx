import { Card } from '../../components/ui/card'
import {
  dedupeReasons,
  formatConfidenceBreakdownDisplay,
  formatDisplayReviewReason,
  formatValidationOutcome,
  getReviewReasonDedupeKey,
} from '../../lib/presentation-safety'
import { formatReviewReason } from '../../lib/review-reason-labels'
import type { ExtractionResponse } from '../../types/qualiflow'



interface ExplanationPanelProps {

  data: ExtractionResponse

  showReviewerFocus?: boolean

}



const CONFIDENCE_LABELS: Record<string, string> = {

  extraction_confidence: 'Document extraction confidence',

  normalization_confidence: 'Normalization confidence',

  spec_resolution_confidence: 'Specification resolution confidence',

  validation_confidence: 'Validation confidence',

  overall_decision_confidence: 'Decision confidence',

}



function formatConfidenceKey(key: string): string {

  return CONFIDENCE_LABELS[key] ?? key.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())

}



function renderMappedList(values: unknown[] | undefined, empty: string) {

  if (!values || values.length === 0) {

    return <p className="text-sm text-slate-400">{empty}</p>

  }



  return (

    <ul className="list-disc space-y-1 pl-5 text-sm text-slate-200">

      {values.map((value, idx) => (

        <li key={idx}>{formatDisplayReviewReason(String(value))}</li>

      ))}

    </ul>

  )

}

function toReasonStrings(values: unknown[] | undefined): string[] {

  return (values ?? []).map((value) => String(value))

}



export function ReviewerFocusStrip({ data }: { data: ExtractionResponse }) {

  const review = (data.explanation?.review_policy ?? {}) as Record<string, unknown>

  const reviewerFocus = review.recommended_reviewer_focus as unknown[] | undefined



  if (!reviewerFocus?.length) return null



  return (

    <Card className="space-y-2 border-amber-900/40 bg-amber-950/20">

      <p className="text-xs font-medium uppercase tracking-wider text-amber-300/90">Reviewer focus</p>

      <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-amber-50">

        {dedupeReasons(toReasonStrings(reviewerFocus)).map((value, idx) => (

          <li key={idx}>{formatDisplayReviewReason(value)}</li>

        ))}

      </ul>

    </Card>

  )

}



export function ExplanationPanel({ data, showReviewerFocus = true }: ExplanationPanelProps) {

  const explanation = data.explanation ?? {}

  const profile = (explanation.document_profile ?? {}) as Record<string, unknown>

  const route = (explanation.route_decision ?? {}) as Record<string, unknown>

  const review = (explanation.review_policy ?? {}) as Record<string, unknown>

  const confidence = data.confidence_breakdown ?? ((explanation.confidence_breakdown ?? {}) as Record<string, number>)

  const topLevelReasons = dedupeReasons(data.review_reasons ?? [])

  const topLevelReasonKeys = new Set(topLevelReasons.map(getReviewReasonDedupeKey))

  const evidenceGaps = dedupeReasons(toReasonStrings(review.evidence_gaps as unknown[] | undefined))

  const evidenceGapKeys = new Set(evidenceGaps.map(getReviewReasonDedupeKey))

  const structuredReasons = dedupeReasons(toReasonStrings(review.review_reasons as unknown[] | undefined))

  const structuredOnlyReasons = structuredReasons.filter((reason) => {

    const key = getReviewReasonDedupeKey(reason)

    return !topLevelReasonKeys.has(key) && !evidenceGapKeys.has(key)

  })

  const reviewSignalsEmptyMessage =

    evidenceGaps.length > 0

      ? 'Primary review drivers are listed below.'

      : 'No additional structured review signals.'



  return (

    <section className="space-y-4">

      {showReviewerFocus && <ReviewerFocusStrip data={data} />}



      <div className="grid gap-4 xl:grid-cols-2">

        <Card className="space-y-2">

          <p className="text-xs uppercase tracking-wider text-slate-400">Validation Outcome</p>

          <p className="text-sm text-slate-200">Outcome: {formatValidationOutcome(data.outcome)}</p>

          {renderMappedList(topLevelReasons, 'No review reasons recorded.')}

        </Card>



        <Card className="space-y-2">

          <p className="text-xs uppercase tracking-wider text-slate-400">Review Signals</p>

          {renderMappedList(

            structuredOnlyReasons.length > 0 ? structuredOnlyReasons : undefined,

            reviewSignalsEmptyMessage,

          )}

          <p className="text-xs uppercase tracking-wider text-slate-500">Evidence Gaps</p>

          {renderMappedList(evidenceGaps, 'No major evidence gaps flagged.')}

        </Card>



        <Card className="space-y-2 xl:col-span-2">

          <p className="text-xs uppercase tracking-wider text-slate-400">Confidence Breakdown</p>

          {confidence && Object.keys(confidence).length > 0 ? (

            <ul className="space-y-1 text-sm text-slate-200">

              {Object.entries(confidence).map(([key, value]) => (

                <li key={key} className="flex justify-between gap-4">

                  <span>{formatConfidenceKey(key)}</span>

                  <span>{formatConfidenceBreakdownDisplay(key, Number(value), data)}</span>

                </li>

              ))}

            </ul>

          ) : (

            <p className="text-sm text-slate-400">No confidence breakdown available.</p>

          )}

        </Card>

      </div>



      <details className="rounded-lg border border-slate-800 bg-slate-950/70">

        <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-300">

          Pipeline diagnostics

        </summary>

        <div className="grid gap-4 border-t border-slate-800 p-4 xl:grid-cols-2">

          <Card className="space-y-2">

            <p className="text-xs uppercase tracking-wider text-slate-400">Document Profile</p>

            <p className="text-sm text-slate-200">Profile: {String(profile.quality_class ?? 'Unknown')}</p>

            <p className="text-sm text-slate-300">

              Reasons:{' '}

              {(profile.reasons as string[] | undefined)?.length

                ? (profile.reasons as string[]).map(formatReviewReason).join('; ')

                : '—'}

            </p>

          </Card>



          <Card className="space-y-2">

            <p className="text-xs uppercase tracking-wider text-slate-400">Route Decision</p>

            <p className="text-sm text-slate-200">Selected: {String(route.selected_route ?? '—')}</p>

            <p className="text-sm text-slate-200">Runtime route: {String(route.runtime_route ?? '—')}</p>

            <p className="text-sm text-slate-300">Strategy: {String(route.expected_strategy ?? '—')}</p>

          </Card>



          <Card className="space-y-2 xl:col-span-2">

            <p className="text-xs uppercase tracking-wider text-slate-400">Evidence / Propagation Notes</p>

            {(explanation.evidence_propagation_notes as unknown[] | undefined)?.length ? (

              <ul className="list-disc space-y-1 pl-5 text-sm text-slate-200">

                {(explanation.evidence_propagation_notes as unknown[]).map((value, idx) => (

                  <li key={idx} className="break-all font-mono text-xs text-slate-300">

                    {JSON.stringify(value)}

                  </li>

                ))}

              </ul>

            ) : (

              <p className="text-sm text-slate-400">No propagated fields or conflicts.</p>

            )}

          </Card>

        </div>

      </details>

    </section>

  )

}


