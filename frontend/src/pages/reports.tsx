import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useDataset } from '../components/shell'
import { Alert, Badge, EmptyState, ErrorNote, Panel, Spinner } from '../components/ui'

export function ReportsTab() {
  const { dataset, versionId } = useDataset()
  const [reports, setReports] = useState<any[]>([])
  const [title, setTitle] = useState(`${dataset.name} — Analysis Report`)
  const [fmt, setFmt] = useState<'pdf' | 'html'>('pdf')
  const [includeCharts, setIncludeCharts] = useState(true)
  const [includeStats, setIncludeStats] = useState(true)
  const [includeConversation, setIncludeConversation] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function load() {
    try { setReports(await api.listReports(dataset.id)) }
    catch (err) { setError(err) }
  }
  useEffect(() => { load() }, [dataset.id])

  async function generate() {
    setBusy(true); setError(null); setNotice(null)
    try {
      const report = await api.generateReport(dataset.id, fmt, title, {
        charts: includeCharts, stats: includeStats, conversation: includeConversation,
      })
      setNotice(`Report generated — ${report.title} (${report.fmt?.toUpperCase() ?? fmt.toUpperCase()})`)
      await load()
    } catch (err) {
      setError(err)
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-6">
      {error ? <ErrorNote error={error} /> : null}
      {notice && <Alert kind="success">{notice}</Alert>}

      <Panel title="Generate a report" subtitle="Built server-side with ReportLab, including real charts and statistics">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className="label" htmlFor="report-title">Title</label>
            <input id="report-title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="report-format">Format</label>
            <select id="report-format" className="select" value={fmt} onChange={(e) => setFmt(e.target.value as any)}>
              <option value="pdf">PDF (ReportLab)</option>
              <option value="html">HTML (standalone)</option>
            </select>
          </div>
          <div className="flex flex-col justify-end gap-2 pb-1">
            {([
              [includeCharts, setIncludeCharts, 'Include charts'],
              [includeStats, setIncludeStats, 'Include statistical analysis'],
              [includeConversation, setIncludeConversation, 'Include NL conversation'],
            ] as const).map(([value, setter, text]) => (
              <label key={text} className="flex items-center gap-2 text-[13px] text-slate-300">
                <input type="checkbox" className="h-3.5 w-3.5 accent-[#3B82F6]" checked={value}
                  onChange={(e) => setter(e.target.checked)} />
                {text}
              </label>
            ))}
          </div>
        </div>

        <div className="mt-4">
          <button className="btn-primary" onClick={generate} disabled={busy || !title.trim()}>
            {busy ? <Spinner /> : null} {busy ? 'Rendering report…' : 'Generate report'}
          </button>
          <p className="mt-2 text-[11px] text-slate-500">
            Reports are written to <code className="text-slate-400">backend/data/reports/</code> and can be re-downloaded at any time.
          </p>
        </div>
      </Panel>

      <Panel title="Generated reports" subtitle={`${reports.length} report${reports.length === 1 ? '' : 's'} for this dataset`}>
        {reports.length === 0 ? (
          <EmptyState title="No reports yet" description="Generate a PDF or HTML report above." />
        ) : (
          <ul className="divide-y divide-white/[0.05]">
            {reports.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-[13px] font-medium text-slate-200">
                    {r.title}
                    <Badge tone={r.fmt === 'pdf' ? 'accent' : 'violet'}>{r.fmt.toUpperCase()}</Badge>
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-500">{new Date(r.created_at).toLocaleString()}</p>
                </div>
                <button
  className="btn-ghost btn-sm"
  onClick={async () => {
    try {
      const blob = await api.downloadReport(r.uid)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${r.title}.${r.fmt}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err)
    }
  }}
>
  Download
</button>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  )
}
