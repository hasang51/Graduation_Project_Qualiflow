import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Card } from '../components/ui/card'
import { ItemsTable } from '../features/results/items-table'
import { SecondaryPanels } from '../features/results/secondary-panels'
import { SummaryCards } from '../features/results/summary-cards'
import { formatConfidence } from '../lib/format'
import { downloadDocument, getAnalysisById } from '../lib/api'

function tone(status: string): 'success' | 'danger' | 'warning' | 'info' {
  if (status === 'COMPLETED') return 'success'
  if (status === 'FAILED') return 'danger'
  if (status === 'NEEDS_REVIEW') return 'warning'
  return 'info'
}

export function AnalysisDetailPage() {
  const params = useParams<{ id: string }>()
  const analysisId = Number(params.id)

  const query = useQuery({
    queryKey: ['analysis', analysisId],
    queryFn: () => getAnalysisById(analysisId),
    enabled: Number.isFinite(analysisId),
  })

  if (query.isLoading) return <Card><p className="text-sm text-slate-300">Loading analysis...</p></Card>
  if (query.isError) return <Card><p className="text-sm text-rose-300">{query.error.message}</p></Card>
  if (!query.data) return <Card><p className="text-sm text-slate-300">Analysis not found.</p></Card>

  const data = query.data

  async function handleDownloadSource() {
    const blob = await downloadDocument(data.document_id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `document-${data.document_id}.pdf`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <Card className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Analysis #{data.id}</h1>
          <p className="text-sm text-slate-400">{new Date(data.created_at).toLocaleString()}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge text={data.status} tone={tone(data.status)} />
          <Badge text={data.extraction_confidence !== null ? formatConfidence(data.extraction_confidence) : 'N/A'} tone="neutral" />
          <Button variant="secondary" onClick={handleDownloadSource}>
            <Download className="mr-2 h-4 w-4" />
            Download PDF
          </Button>
        </div>
      </Card>

      {data.error_message && (
        <Card className="border-rose-900/70 bg-rose-950/20">
          <p className="text-sm text-rose-200">{data.error_message}</p>
        </Card>
      )}

      {data.extraction ? (
        <>
          <SummaryCards data={data.extraction} />
          <ItemsTable items={data.extraction.items} />
          <SecondaryPanels data={data.extraction} />
        </>
      ) : (
        <Card>
          <p className="text-sm text-slate-300">Extraction payload is unavailable for this run.</p>
        </Card>
      )}
    </div>
  )
}
