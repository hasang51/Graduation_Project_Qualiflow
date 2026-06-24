import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, RefreshCw, ShieldCheck, Upload } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../../components/ui/button'
import { Card } from '../../components/ui/card'
import { ItemsTable } from '../results/items-table'
import { ExplanationPanel, ReviewerFocusStrip } from '../results/explanation-panel'
import { SecondaryPanels } from '../results/secondary-panels'
import { SummaryCards } from '../results/summary-cards'
import { UploadDropzone } from '../upload/upload-dropzone'
import { extractDocumentAsync, getHealth, type JobProgressPhase } from '../../lib/api'
import { buildItemsCsv } from '../../lib/csv'
import type { ExtractionResponse } from '../../types/qualiflow'
import { AnalysisProgress } from './analysis-progress'

const loadingSteps = [
  'Uploading PDF',
  'Queued for processing',
  'Processing pages',
  'Extracting structured data',
  'Validating compliance',
]

function phaseToStepIndex(phase: JobProgressPhase): number {
  switch (phase) {
    case 'uploading':
      return 0
    case 'queued':
      return 1
    case 'processing':
      return 2
    case 'succeeded':
      return loadingSteps.length - 1
    default:
      return 2
  }
}

function downloadCsv(content: string) {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'qualiflow-items.csv'
  link.click()
  URL.revokeObjectURL(url)
}

export function AnalyzeWorkspace() {
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [result, setResult] = useState<ExtractionResponse | null>(null)
  const [openingReport, setOpeningReport] = useState(false)
  const [loadingStepIndex, setLoadingStepIndex] = useState(0)

  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    retry: 1,
  })

  const mutation = useMutation({
    mutationFn: (selectedFile: File) =>
      extractDocumentAsync(selectedFile, true, (phase) => {
        setLoadingStepIndex(phaseToStepIndex(phase))
      }),
    onSuccess: ({ extraction, analysisId }) => {
      if (analysisId !== null) {
        setOpeningReport(true)
        navigate(`/analysis/${analysisId}`, { replace: true })
        return
      }
      console.info('Analysis completed without a saved analysis id; showing inline results.')
      setResult(extraction)
    },
  })

  function onFileSelected(nextFile: File | null, error?: string) {
    setFile(nextFile)
    setFileError(error ?? null)
  }

  function analyzeDocument() {
    if (!file) {
      setFileError('Please choose a PDF file before analysis.')
      return
    }
    setResult(null)
    setOpeningReport(false)
    setLoadingStepIndex(0)
    mutation.mutate(file)
  }

  const canSubmit = Boolean(file) && !fileError && !mutation.isPending && !healthQuery.isError

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-sky-400">Industrial Document Extraction</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-50">QualiFlow</h1>
          <p className="mt-2 max-w-2xl text-slate-400">
            Upload a manufacturing PDF and persist compliance analysis in your local database.
          </p>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/80 px-3 py-2 text-sm text-slate-300">
          {healthQuery.isLoading ? 'Checking backend health...' : healthQuery.isError ? 'Backend offline' : 'Backend online'}
        </div>
      </header>

      {healthQuery.isError && (
        <Card className="border-rose-900/70 bg-rose-950/20">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 text-rose-300" />
              <p className="text-sm text-rose-100">
                {healthQuery.error instanceof Error
                  ? healthQuery.error.message
                  : 'Cannot reach the backend API. Verify the server is running and VITE_API_BASE_URL is correct.'}
              </p>
            </div>
            <Button variant="danger" className="h-9" onClick={() => healthQuery.refetch()}>
              Retry Health Check
            </Button>
          </div>
        </Card>
      )}

      {openingReport && (
        <Card>
          <p className="text-sm text-slate-300">Analysis completed. Opening detailed report...</p>
        </Card>
      )}

      {!result && !openingReport && (
        <div className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
          <Card className="space-y-4">
            <div className="flex items-center gap-2">
              <Upload className="h-4 w-4 text-sky-400" />
              <h2 className="text-lg font-semibold">Document Upload</h2>
            </div>
            <UploadDropzone file={file} onFileSelected={onFileSelected} disabled={mutation.isPending} />

            {fileError && <p className="rounded-md border border-rose-800/70 bg-rose-950/25 px-3 py-2 text-sm text-rose-200">{fileError}</p>}
            {mutation.isError && (
              <div className="rounded-md border border-rose-800/70 bg-rose-950/25 px-3 py-2 text-sm text-rose-200">
                {mutation.error.message}
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button onClick={analyzeDocument} disabled={!canSubmit}>
                <ShieldCheck className="mr-2 h-4 w-4" />
                Analyze Document
              </Button>
              {mutation.isError && (
                <Button variant="secondary" onClick={() => mutation.reset()}>
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Retry
                </Button>
              )}
            </div>
          </Card>
          <AnalysisProgress
            currentStepIndex={mutation.isPending ? loadingStepIndex : 0}
            active={mutation.isPending}
            steps={loadingSteps}
          />
        </div>
      )}

      {result && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-xl font-semibold text-slate-100">Extraction Results</h2>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => setResult(null)}>
                Analyze another PDF
              </Button>
              <Button variant="ghost" onClick={() => downloadCsv(buildItemsCsv(result.items))}>
                Export CSV
              </Button>
            </div>
          </div>
          <SummaryCards data={result} />
          <ItemsTable
            items={result.items}
            reviewReasons={result.review_reasons}
            explanation={result.explanation}
          />
          <ReviewerFocusStrip data={result} />
          <details className="rounded-lg border border-slate-800 bg-slate-950/70">
            <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-200">
              Technical details
            </summary>
            <div className="space-y-6 border-t border-slate-800 p-4">
              <ExplanationPanel data={result} showReviewerFocus={false} />
              <SecondaryPanels data={result} />
            </div>
          </details>
        </div>
      )}
    </div>
  )
}
