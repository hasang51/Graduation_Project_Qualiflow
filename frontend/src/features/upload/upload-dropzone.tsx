import { FileText, UploadCloud } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { formatBytes } from '../../lib/format'
import { cn } from '../../lib/utils'

interface UploadDropzoneProps {
  file: File | null
  onFileSelected: (file: File | null, error?: string) => void
  disabled?: boolean
}

function isPdf(file: File): boolean {
  return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
}

export function UploadDropzone({ file, onFileSelected, disabled }: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  function processFile(nextFile: File | null) {
    if (!nextFile) {
      onFileSelected(null)
      return
    }

    if (!isPdf(nextFile)) {
      onFileSelected(null, 'Unsupported file type. Please upload a PDF document.')
      return
    }

    onFileSelected(nextFile)
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setIsDragging(false)
    if (disabled) return
    processFile(event.dataTransfer.files?.[0] ?? null)
  }

  return (
    <div className="space-y-3">
      <div
        role="button"
        tabIndex={0}
        onClick={() => !disabled && inputRef.current?.click()}
        onDrop={onDrop}
        onDragOver={(event) => {
          event.preventDefault()
          if (!disabled) setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            if (!disabled) inputRef.current?.click()
          }
        }}
        className={cn(
          'group relative flex min-h-48 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-900/70 p-6 text-center transition',
          'hover:border-sky-500/70 hover:bg-slate-900',
          isDragging && 'border-sky-500 bg-slate-900',
          disabled && 'cursor-not-allowed opacity-60',
        )}
      >
        <UploadCloud className="mb-4 h-10 w-10 text-sky-400 transition group-hover:scale-105" />
        <p className="text-base font-semibold text-slate-100">Drop PDF here or click to select</p>
        <p className="mt-2 text-sm text-slate-400">Single file upload, PDF only</p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={(event) => processFile(event.target.files?.[0] ?? null)}
          disabled={disabled}
        />
      </div>

      {file && (
        <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm">
          <div className="flex items-center gap-2 text-slate-200">
            <FileText className="h-4 w-4 text-sky-400" />
            <span className="max-w-[320px] truncate">{file.name}</span>
          </div>
          <span className="text-slate-400">{formatBytes(file.size)}</span>
        </div>
      )}
    </div>
  )
}
