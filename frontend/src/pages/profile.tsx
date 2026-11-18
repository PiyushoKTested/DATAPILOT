import { useEffect, useState } from 'react'
import { api, formatBytes, formatNumber, type ProfileResponse } from '../lib/api'
import { useDataset } from '../components/shell'
import { Badge, Bullets, DataTable, EmptyState, ErrorNote, KpiCard, Panel, Spinner } from '../components/ui'

export function ProfileTab() {
  const { dataset, versionId } = useDataset()
  const [data, setData] = useState<ProfileResponse | null>(null)
  const [preview, setPreview] = useState<any>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    let cancelled = false
    setData(null)
    setPreview(null)
    ;(async () => {
      try {
        const [profile, rows] = await Promise.all([
          api.profile(dataset.id, versionId),
          api.preview(dataset.id, versionId, 50),
        ])
        if (!cancelled) { setData(profile); setPreview(rows) }
      } catch (err) {
        if (!cancelled) setError(err)
      }
    })()
    return () => { cancelled = true }
  }, [dataset.id, versionId])

  if (error) return <ErrorNote error={error} />
  if (!data || !preview) return <div className="flex items-center gap-3 py-16 text-sm text-slate-400"><Spinner /> Profiling dataset…</div>

  const { profile } = data
  const quality = profile.quality
  const gradeTone = quality.grade.startsWith('A') ? 'good' : quality.grade.startsWith('B') ? 'good' : quality.grade.startsWith('C') ? 'warn' : 'bad'

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Rows" value={profile.shape.rows.toLocaleString()} />
        <KpiCard label="Columns" value={profile.shape.columns} hint={`${profile.column_groups.numeric.length} numeric`} />
        <KpiCard label="Missing cells" value={profile.missing_total.toLocaleString()} hint={`${profile.missing_by_column.length} affected columns`} />
        <KpiCard
          label="Quality score"
          value={`${formatNumber(quality.score, 1)}`}
          hint={`Grade ${quality.grade}`}
          tone={gradeTone as any}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Quality breakdown" subtitle={quality.methodology}>
          <div className="space-y-3">
            {Object.entries(quality.weights).map(([key, weight]) => {
              const value = quality.components[key] ?? 0
              return (
                <div key={key}>
                  <div className="flex items-baseline justify-between text-xs">
                    <span className="capitalize text-slate-300">{key.replace(/_/g, ' ')}</span>
                    <span className="num text-slate-400">
                      {formatNumber(value, 1)} <span className="text-slate-600">× {weight}</span>
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                    <div
                      className={`h-full rounded-full ${value >= 80 ? 'bg-emerald-400' : value >= 60 ? 'bg-amber-400' : 'bg-red-400'}`}
                      style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
                    />
                  </div>
                </div>
              )
            })}
            {quality.issues.length > 0 && (
              <div className="pt-2"><Bullets items={quality.issues} tone="warn" /></div>
            )}
          </div>
        </Panel>

        <Panel title="Key findings" subtitle="Generated from computed statistics only">
          {data.findings.length ? <Bullets items={data.findings} /> : <p className="text-xs text-slate-500">No notable findings.</p>}
          <div className="mt-4 flex flex-wrap gap-2 border-t border-white/[0.06] pt-4">
            <span className="chip">Duplicates: {profile.duplicates.duplicate_rows.toLocaleString()} ({profile.duplicates.duplicate_pct}%)</span>
            <span className="chip">Memory: {formatBytes(profile.memory_bytes)}</span>
            <span className="chip">{profile.column_groups.datetime.length} datetime</span>
            <span className="chip">{profile.column_groups.categorical.length} categorical</span>
          </div>
        </Panel>
      </div>

      <Panel
        title="Column profile"
        subtitle={`${profile.columns.length} columns · types detected automatically`}
      >
        <div className="overflow-auto rounded-lg border border-white/[0.06]" style={{ maxHeight: 460 }}>
          <table className="min-w-full">
            <thead className="sticky top-0 z-10 bg-navy-900">
              <tr>
                {['Column', 'Type', 'Kind', 'Missing', 'Unique', 'Mean', 'Median', 'Std', 'Min', 'Max'].map((h, i) => (
                  <th key={h} className={i > 3 ? 'th text-right' : 'th'}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {profile.columns.map((col) => {
                const s = col.stats ?? {}
                return (
                  <tr key={col.name} className="hover:bg-white/[0.03]">
                    <td className="td font-medium text-slate-100">{col.name}</td>
                    <td className="td text-slate-400">{col.pandas_dtype}</td>
                    <td className="td"><Badge tone={col.kind === 'numeric' ? 'accent' : col.kind === 'datetime' ? 'violet' : 'neutral'}>{col.kind}</Badge></td>
                    <td className="td text-right">
                      {col.missing > 0 ? <span className="text-amber-300">{col.missing} ({col.missing_pct}%)</span> : <span className="text-slate-500">0</span>}
                    </td>
                    <td className="td num text-right">{col.unique.toLocaleString()}</td>
                    <td className="td num text-right">{s.mean != null ? formatNumber(s.mean, 3) : '—'}</td>
                    <td className="td num text-right">{s.median != null ? formatNumber(s.median, 3) : '—'}</td>
                    <td className="td num text-right">{s.std != null ? formatNumber(s.std, 3) : '—'}</td>
                    <td className="td num text-right">{s.min != null ? formatNumber(s.min, 3) : '—'}</td>
                    <td className="td num text-right">{s.max != null ? formatNumber(s.max, 3) : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      {data.numeric_summary.length > 0 && (
        <Panel title="Numeric summary" subtitle="Computed with pandas (ddof = 1)" >
          <DataTable columns={Object.keys(data.numeric_summary[0])} rows={data.numeric_summary} maxHeight={380} />
        </Panel>
      )}

      <Panel title="Data preview" subtitle={`First ${preview.returned_rows} of ${preview.total_rows.toLocaleString()} rows`}>
        {preview.rows.length ? (
          <DataTable columns={preview.columns} rows={preview.rows} maxHeight={420} />
        ) : (
          <EmptyState title="This version has no rows" />
        )}
      </Panel>

      {data.recommendations.length > 0 && (
        <Panel title="Suggested cleaning steps" subtitle="Open the Clean tab to apply any of these">
          <ul className="space-y-2">
            {data.recommendations.slice(0, 8).map((rec: any, i: number) => (
              <li key={i} className="flex flex-wrap items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
                <Badge tone={rec.severity === 'high' ? 'bad' : 'warn'}>{rec.severity}</Badge>
                <span className="text-[13px] text-slate-300">{rec.reason}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  )
}
