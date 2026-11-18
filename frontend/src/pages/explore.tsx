import { useEffect, useState } from 'react'
import { api, formatNumber, type ChartPayload } from '../lib/api'
import { useDataset } from '../components/shell'
import { ChartRenderer } from '../components/chart'
import { Alert, Badge, EmptyState, ErrorNote, KeyValues, Panel, Spinner } from '../components/ui'

const CHART_TYPES = [
  { value: 'histogram', label: 'Histogram' },
  { value: 'bar', label: 'Bar chart' },
  { value: 'pie', label: 'Pie chart' },
  { value: 'scatter', label: 'Scatter plot' },
  { value: 'box', label: 'Box plot' },
  { value: 'line', label: 'Line / trend' },
  { value: 'grouped_aggregate', label: 'Grouped aggregate' },
  { value: 'correlation_heatmap', label: 'Correlation heatmap' },
]

export function ExploreTab() {
  const { dataset, versionId } = useDataset()
  const [columns, setColumns] = useState<{ numeric: string[]; categorical: string[]; datetime: string[]; text: string[] } | null>(null)
  const [suggestions, setSuggestions] = useState<any[]>([])
  const [chartType, setChartType] = useState('histogram')
  const [x, setX] = useState('')
  const [y, setY] = useState('')
  const [groupBy, setGroupBy] = useState('')
  const [agg, setAgg] = useState('mean')
  const [chart, setChart] = useState<ChartPayload | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [cols, sug] = await Promise.all([
          api.columns(dataset.id, versionId),
          api.chartSuggestions(dataset.id, versionId),
        ])
        if (cancelled) return
        setColumns(cols.column_groups)
        setSuggestions(sug.suggestions)
        setX(cols.column_groups.numeric[0] ?? cols.column_groups.categorical[0] ?? '')
        setY(cols.column_groups.numeric[1] ?? '')
        setGroupBy(cols.column_groups.categorical[0] ?? '')
      } catch (err) {
        if (!cancelled) setError(err)
      }
    })()
    return () => { cancelled = true }
  }, [dataset.id, versionId])

  async function build(overrides: Partial<Record<string, any>> = {}) {
    const type = overrides.chart_type ?? chartType
    const payload: any = { chart_type: type, top_n: 12, bins: 20 }
    if (type === 'histogram') payload.x = overrides.x ?? x
    else if (type === 'bar') payload.x = overrides.x ?? x ?? groupBy
    else if (type === 'pie') payload.x = overrides.x ?? groupBy
    else if (type === 'scatter') { payload.x = overrides.x ?? x; payload.y = overrides.y ?? y }
    else if (type === 'box') { payload.x = overrides.x ?? x; payload.group_by = overrides.group_by ?? (groupBy || undefined) }
    else if (type === 'line') { payload.x = overrides.x ?? (columns?.datetime[0] ?? ''); payload.y = overrides.y ?? (y || undefined) }
    else if (type === 'grouped_aggregate') { payload.group_by = overrides.group_by ?? groupBy; payload.y = overrides.y ?? y; payload.agg = overrides.agg ?? agg }

    setBusy(true); setError(null)
    try {
      const result = await api.createChart(dataset.id, { ...payload, version_id: versionId })
      setChart(result)
    } catch (err) {
      setChart(null)
      setError(err)
    } finally { setBusy(false) }
  }

  if (!columns) return <div className="flex items-center gap-3 py-16 text-sm text-slate-400"><Spinner /> Loading columns…</div>

  const numeric = columns.numeric
  const categorical = [...columns.categorical, ...columns.text]
  const datetimes = columns.datetime

  const needsX = ['histogram', 'bar', 'pie', 'scatter', 'box'].includes(chartType)
  const needsY = ['scatter', 'grouped_aggregate'].includes(chartType)
  const needsGroup = chartType === 'grouped_aggregate'
  const xOptions = chartType === 'bar' || chartType === 'pie' ? [...categorical, ...numeric] : chartType === 'line' ? datetimes : numeric.length ? numeric : categorical

  return (
    <div className="space-y-6">
      {error ? <ErrorNote error={error} /> : null}

      <Panel title="Build a chart" subtitle="Every point comes from a real aggregation of this version">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="label" htmlFor="chart-type">Chart type</label>
            <select id="chart-type" className="select" value={chartType} onChange={(e) => setChartType(e.target.value)}>
              {CHART_TYPES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </div>

          {needsX && (
            <div>
              <label className="label" htmlFor="chart-x">{chartType === 'line' ? 'Date column' : 'X column'}</label>
              <select id="chart-x" className="select" value={x} onChange={(e) => setX(e.target.value)}>
                {xOptions.length === 0 && <option value="">No compatible columns</option>}
                {xOptions.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          )}

          {(needsY || chartType === 'line') && (
            <div>
              <label className="label" htmlFor="chart-y">Value column</label>
              <select id="chart-y" className="select" value={y} onChange={(e) => setY(e.target.value)}>
                <option value="">Row count</option>
                {numeric.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          )}

          {(needsGroup || chartType === 'box') && (
            <div>
              <label className="label" htmlFor="chart-group">Group by</label>
              <select id="chart-group" className="select" value={groupBy} onChange={(e) => setGroupBy(e.target.value)}>
                <option value="">None</option>
                {categorical.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          )}

          {needsGroup && (
            <div>
              <label className="label" htmlFor="chart-agg">Aggregation</label>
              <select id="chart-agg" className="select" value={agg} onChange={(e) => setAgg(e.target.value)}>
                {['mean', 'median', 'sum', 'count', 'min', 'max'].map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
          )}
        </div>

        <div className="mt-4 flex items-center gap-2">
          <button className="btn-primary" onClick={() => build()} disabled={busy}>
            {busy ? <Spinner /> : null} Generate chart
          </button>
          {chart && <span className="text-[11px] text-slate-500">Rendered from {chart.data?.length ?? chart.series?.length ?? 0} computed buckets</span>}
        </div>
      </Panel>

      {suggestions.length > 0 && (
        <Panel title="Suggested charts" subtitle="Click to render immediately">
          <div className="flex flex-wrap gap-2">
            {suggestions.map((s, i) => (
              <button
                key={i}
                className="chip transition hover:border-accent/40 hover:bg-accent/10 hover:text-white"
                onClick={() => {
                  setChartType(s.chart_type)
                  if (s.x) setX(s.x)
                  if (s.y) setY(s.y)
                  if (s.group_by) setGroupBy(s.group_by)
                  build(s)
                }}
              >
                <span className="text-accent-soft">{s.chart_type.replace(/_/g, ' ')}</span>
                <span className="text-slate-500">·</span>
                {s.reason}
              </button>
            ))}
          </div>
        </Panel>
      )}

      <Panel
        title={chart?.title ?? 'Chart'}
        subtitle={chart?.note ?? (chart?.sampled ? `Sampled ${chart.data?.length} of ${(chart as any).total_points} points` : undefined)}
        actions={chart ? <Badge tone="accent">{chart.chart_type.replace(/_/g, ' ')}</Badge> : undefined}
      >
        {busy && !chart && <div className="flex items-center gap-3 py-10 text-sm text-slate-400"><Spinner /> Computing…</div>}
        {!busy && !chart && <EmptyState title="No chart yet" description="Pick a chart type and column, then press Generate chart." />}
        {chart && <ChartRenderer chart={chart} height={380} />}
        {chart?.stats && (
          <div className="mt-4 border-t border-white/[0.06] pt-4">
            <KeyValues data={chart.stats} columns={3} />
          </div>
        )}
        {chart?.pearson_r != null && (
          <p className="mt-3 text-xs text-slate-400">
            Pearson r = <span className="num text-slate-100">{formatNumber(chart.pearson_r, 4)}</span>
          </p>
        )}
      </Panel>

      {chart?.data && ['histogram', 'bar', 'pie', 'grouped_aggregate', 'line'].includes(chart.chart_type) && (
        <Panel title="Underlying values" subtitle="The exact numbers behind the chart">
          <div className="overflow-auto" style={{ maxHeight: 320 }}>
            <table className="min-w-full">
              <thead className="sticky top-0 bg-navy-900">
                <tr>
                  <th className="th">Label</th>
                  <th className="th text-right">Value</th>
                  {(chart.data[0] as any)?.count != null && <th className="th text-right">Count</th>}
                </tr>
              </thead>
              <tbody>
                {chart.data.map((d, i) => (
                  <tr key={i}>
                    <td className="td">{d.label}</td>
                    <td className="td num text-right">{formatNumber(d.value, 4)}</td>
                    {(d as any).count != null && <td className="td num text-right">{formatNumber((d as any).count, 0)}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {columns.numeric.length === 0 && (
        <Alert kind="warn">This version has no numeric columns, so numeric charts are unavailable. Type corrections in the Clean tab can help.</Alert>
      )}
    </div>
  )
}
