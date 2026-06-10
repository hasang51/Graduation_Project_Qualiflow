import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../components/ui/badge'
import { Card } from '../components/ui/card'
import { Input } from '../components/ui/input'
import { formatConfidence } from '../lib/format'
import { getAnalyses } from '../lib/api'

function statusTone(status: string): 'info' | 'success' | 'danger' | 'warning' {
  if (status === 'COMPLETED') return 'success'
  if (status === 'FAILED') return 'danger'
  if (status === 'NEEDS_REVIEW') return 'warning'
  return 'info'
}

export function HistoryPage() {
  const [search, setSearch] = useState('')
  const query = useQuery({ queryKey: ['analyses'], queryFn: getAnalyses })

  const rows = useMemo(() => {
    if (!query.data) return []
    const term = search.trim().toLowerCase()
    return query.data.filter((row) => {
      if (!term) return true
      return [row.supplier_name, row.document_type, row.status].some((value) => (value || '').toLowerCase().includes(term))
    })
  }, [query.data, search])

  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Analysis History</h1>
          <p className="text-sm text-slate-400">Review saved extraction and compliance runs.</p>
        </div>
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <Input value={search} onChange={(event) => setSearch(event.target.value)} className="pl-9" placeholder="Search analyses..." />
        </div>
      </Card>

      {query.isLoading && <Card><p className="text-sm text-slate-300">Loading analyses...</p></Card>}
      {query.isError && <Card><p className="text-sm text-rose-300">{query.error.message}</p></Card>}
      {!query.isLoading && rows.length === 0 && <Card><p className="text-sm text-slate-300">No analyses found.</p></Card>}

      <div className="space-y-3">
        {rows.map((row) => (
          <Card key={row.id} className="flex flex-wrap items-center justify-between gap-3">
            <div className="space-y-1">
              <p className="font-semibold text-slate-100">{row.supplier_name || 'Unknown supplier'}</p>
              <p className="text-sm text-slate-400">{row.document_type || 'Unknown document'} • {row.total_items_detected ?? 0} items</p>
              <p className="text-xs text-slate-500">{new Date(row.created_at).toLocaleString()}</p>
            </div>
            <div className="flex items-center gap-2">
              <Badge text={row.status} tone={statusTone(row.status)} />
              <Badge text={row.extraction_confidence !== null ? formatConfidence(row.extraction_confidence) : 'N/A'} tone="neutral" />
              <Link className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800" to={`/analysis/${row.id}`}>
                Open
              </Link>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
