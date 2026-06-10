import { useQuery } from '@tanstack/react-query'

import { CheckCheck, Clipboard, Download } from 'lucide-react'

import { useState } from 'react'

import { useParams } from 'react-router-dom'

import { Badge } from '../components/ui/badge'

import { Button } from '../components/ui/button'

import { Card } from '../components/ui/card'

import { ItemsTable } from '../features/results/items-table'

import { ExplanationPanel, ReviewerFocusStrip } from '../features/results/explanation-panel'

import { SecondaryPanels } from '../features/results/secondary-panels'

import { SummaryCards } from '../features/results/summary-cards'

import {

  EXTRACTION_CONFIDENCE_CAPTION,

  formatConfidence,


  getRoutingDecisionDisplayTone,

  getRoutingDecisionLabel,

} from '../lib/format'

import {

  getCompliantNeedsReviewNote,
  getPresentationConfidenceHelperText,
  getPresentationSpecificationCheckDisplay,
  resolveDecisionConfidence,
} from '../lib/presentation-safety'

import { downloadDocument, getAnalysisById } from '../lib/api'



function tone(status: string): 'success' | 'danger' | 'warning' | 'info' {

  if (status === 'COMPLETED') return 'success'

  if (status === 'FAILED') return 'danger'

  if (status === 'NEEDS_REVIEW') return 'warning'

  return 'info'

}



function confidenceTone(score: number): 'success' | 'warning' | 'danger' {

  if (score >= 0.85) return 'success'

  if (score >= 0.6) return 'warning'

  return 'danger'

}



function downloadTextFile(filename: string, content: string, mimeType: string) {

  const blob = new Blob([content], { type: mimeType })

  const url = URL.createObjectURL(blob)

  const anchor = document.createElement('a')

  anchor.href = url

  anchor.download = filename

  anchor.click()

  URL.revokeObjectURL(url)

}



export function AnalysisDetailPage() {

  const params = useParams<{ id: string }>()

  const analysisId = Number(params.id)

  const [copied, setCopied] = useState(false)



  const query = useQuery({

    queryKey: ['analysis', analysisId],

    queryFn: () => getAnalysisById(analysisId),

    enabled: Number.isFinite(analysisId),

  })



  if (query.isLoading) return <Card><p className="text-sm text-slate-300">Loading analysis...</p></Card>

  if (query.isError) return <Card><p className="text-sm text-rose-300">{query.error.message}</p></Card>

  if (!query.data) return <Card><p className="text-sm text-slate-300">Analysis not found.</p></Card>



  const data = query.data

  const extraction = data.extraction

  const rawJson = extraction ? JSON.stringify(extraction, null, 2) : ''

  const specificationDisplay = extraction ? getPresentationSpecificationCheckDisplay(extraction) : null

  const routingDecision = extraction ? getRoutingDecisionLabel(extraction) : null

  const confidenceHelper = extraction ? getPresentationConfidenceHelperText(extraction) : null

  const showCompliantNeedsReviewNote =

    specificationDisplay?.label === 'Compliant' && routingDecision === 'Needs human review'



  async function handleDownloadSource() {

    const blob = await downloadDocument(data.document_id)

    const url = URL.createObjectURL(blob)

    const link = document.createElement('a')

    link.href = url

    link.download = `document-${data.document_id}.pdf`

    link.click()

    URL.revokeObjectURL(url)

  }



  async function copyJson() {

    if (!rawJson) return

    await navigator.clipboard.writeText(rawJson)

    setCopied(true)

    setTimeout(() => setCopied(false), 1200)

  }



  function downloadJson() {

    if (!rawJson) return

    downloadTextFile('qualiflow-extraction.json', rawJson, 'application/json')

  }



  return (

    <div className="space-y-6">

      <Card className="space-y-4">

        <div className="flex flex-wrap items-center justify-between gap-3">

          <div>

            <h1 className="text-xl font-semibold text-slate-100">Analysis #{data.id}</h1>

            <p className="text-sm text-slate-400">{new Date(data.created_at).toLocaleString()}</p>

          </div>

          <div className="flex flex-wrap items-center gap-2">

            <Badge text={data.status} tone={tone(data.status)} />

            <Button variant="secondary" onClick={handleDownloadSource}>

              <Download className="mr-2 h-4 w-4" />

              Download PDF

            </Button>

            {extraction && (

              <>

                <Button variant="secondary" onClick={copyJson} className="h-9">

                  {copied ? <CheckCheck className="mr-2 h-4 w-4" /> : <Clipboard className="mr-2 h-4 w-4" />}

                  {copied ? 'Copied' : 'Copy JSON'}

                </Button>

                <Button variant="ghost" onClick={downloadJson} className="h-9">

                  <Download className="mr-2 h-4 w-4" />

                  Download JSON

                </Button>

              </>

            )}

          </div>

        </div>



        {extraction && specificationDisplay && routingDecision && (

          <div className="space-y-3 border-t border-slate-800 pt-4">

            <div className="grid gap-4 md:grid-cols-3">

              <div className="space-y-1">

                <p className="text-xs uppercase tracking-wider text-slate-500">Rule-based compliance check</p>

                <Badge text={specificationDisplay.label} tone={specificationDisplay.tone} />

                {specificationDisplay.reason && (

                  <p className="text-xs leading-relaxed text-slate-400">

                    Reason: {specificationDisplay.reason}

                  </p>

                )}

              </div>

              <div className="space-y-1">

                <p className="text-xs uppercase tracking-wider text-slate-500">Final routing decision</p>

                <Badge text={routingDecision} tone={getRoutingDecisionDisplayTone(routingDecision)} />

              </div>

              <div className="space-y-1">

                <p className="text-xs uppercase tracking-wider text-slate-500">Decision Confidence</p>

                <Badge

                  text={formatConfidence(resolveDecisionConfidence(extraction))}

                  tone={confidenceTone(resolveDecisionConfidence(extraction))}

                />

                <p className="text-xs leading-relaxed text-slate-500">{EXTRACTION_CONFIDENCE_CAPTION}</p>

                {confidenceHelper && (

                  <p className="text-xs leading-relaxed text-slate-400">{confidenceHelper}</p>

                )}

              </div>

            </div>

            {showCompliantNeedsReviewNote && (

              <p className="text-sm leading-relaxed text-slate-400">

                {getCompliantNeedsReviewNote(extraction!)}

              </p>

            )}

          </div>

        )}

      </Card>



      {data.error_message && (

        <Card className="border-rose-900/70 bg-rose-950/20">

          <p className="text-sm text-rose-200">{data.error_message}</p>

        </Card>

      )}



      {extraction ? (

        <>

          <SummaryCards data={extraction} variant="detail" />

          <ItemsTable

            items={extraction.items}

            reviewReasons={extraction.review_reasons}

            explanation={extraction.explanation}

            emptyMessage="No reliable line items were extracted. The document was routed to human review."

          />

          <ReviewerFocusStrip data={extraction} />

          <details className="rounded-lg border border-slate-800 bg-slate-950/70">

            <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-200">

              Technical details

            </summary>

            <div className="space-y-6 border-t border-slate-800 p-4">

              <ExplanationPanel data={extraction} showReviewerFocus={false} />

              <SecondaryPanels data={extraction} />

            </div>

          </details>

        </>

      ) : (

        <Card>

          <p className="text-sm text-slate-300">Extraction payload is unavailable for this run.</p>

        </Card>

      )}

    </div>

  )

}


