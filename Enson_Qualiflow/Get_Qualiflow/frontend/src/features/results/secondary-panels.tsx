import { CheckCheck, Clipboard, Download, FileJson } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Button } from '../../components/ui/button'
import { Card } from '../../components/ui/card'
import type { ExtractionResponse } from '../../types/qualiflow'

interface SecondaryPanelsProps {
  data: ExtractionResponse
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

export function SecondaryPanels({ data }: SecondaryPanelsProps) {
  const [copied, setCopied] = useState(false)
  const rawJson = useMemo(() => JSON.stringify(data, null, 2), [data])

  const allDeviations = useMemo(() => {
    return data.items.flatMap((item, index) =>
      (item.validation?.deviations ?? []).map((deviation) => ({
        itemId: item.item_id || `row-${index + 1}`,
        message: deviation,
      })),
    )
  }, [data.items])

  async function copyJson() {
    await navigator.clipboard.writeText(rawJson)
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }

  function downloadJson() {
    downloadTextFile('qualiflow-extraction.json', rawJson, 'application/json')
  }

  return (
    <section className="grid gap-4 xl:grid-cols-3">
      <Card className="space-y-3 xl:col-span-1">
        <p className="text-xs uppercase tracking-wider text-slate-400">AI Analysis Remarks</p>
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
          {data.ai_analysis_remarks || 'No additional AI remarks were returned for this document.'}
        </p>
      </Card>

      <Card className="space-y-3 xl:col-span-1">
        <p className="text-xs uppercase tracking-wider text-slate-400">Validation Findings</p>
        {allDeviations.length > 0 ? (
          <ul className="max-h-60 space-y-2 overflow-auto text-sm text-slate-200">
            {allDeviations.map((deviation, index) => (
              <li key={`${deviation.itemId}-${index}`} className="rounded-md border border-slate-800 bg-slate-900 p-2">
                <span className="mr-2 text-slate-500">[{deviation.itemId}]</span>
                {deviation.message}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-300">No deviations detected.</p>
        )}
      </Card>

      <Card className="space-y-3 xl:col-span-1">
        <p className="text-xs uppercase tracking-wider text-slate-400">Raw JSON</p>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={copyJson} className="h-9">
            {copied ? <CheckCheck className="mr-2 h-4 w-4" /> : <Clipboard className="mr-2 h-4 w-4" />}
            {copied ? 'Copied' : 'Copy JSON'}
          </Button>
          <Button variant="ghost" onClick={downloadJson} className="h-9">
            <Download className="mr-2 h-4 w-4" />
            Download JSON
          </Button>
        </div>

        <details className="rounded-lg border border-slate-800 bg-slate-950/70">
          <summary className="cursor-pointer list-none px-3 py-2 text-sm text-slate-300">
            <span className="inline-flex items-center gap-2">
              <FileJson className="h-4 w-4 text-slate-500" />
              Show raw response payload
            </span>
          </summary>
          <pre className="max-h-64 overflow-auto border-t border-slate-800 px-3 py-2 text-xs text-slate-300">
            {rawJson}
          </pre>
        </details>
      </Card>
    </section>
  )
}
