import { useEffect, useState } from 'react'
import { api, formatNumber } from '../lib/api'
import { useDataset } from '../components/shell'
import { Alert, Badge, Bullets, EmptyState, ErrorNote, KeyValues, Panel, Spinner } from '../components/ui'

const TESTS = [
  { value: 'pearson', label: 'Pearson correlation', needs: ['x', 'y'] },
  { value: 'spearman', label: 'Spearman correlation', needs: ['x', 'y'] },
  { value: 'ttest_ind', label: "Welch's t-test (independent)", needs: ['x', 'group_column', 'group_a', 'group_b'] },
  { value: 'ttest_rel', label: 'Paired t-test', needs: ['x', 'y'] },
  { value: 'ttest_1samp', label: 'One-sample t-test', needs: ['x', 'popmean'] },
  { value: 'chi_square', label: 'Chi-square independence', needs: ['x', 'y'] },
  { value: 'anova', label: 'One-way ANOVA', needs: ['x', 'group_column'] },
]

export function StatsTab() {
  const { dataset, versionId } = useDataset()
  const [columns, setColumns] = useState<any>(null)
  const [descriptive, setDescriptive] = useState<any>(null)
  const [insights, setInsights] = useState<any>(null)
  const [test, setTest] = useState('pearson')
  const [x, setX] = useState('')
  const [y, setY] = useState('')
  const [groupColumn, setGroupColumn] = useState('')
  const [groupA, setGroupA] = useState('')
  const [groupB, setGroupB] = useState('')
  const [popmean, setPopmean] = useState('0')
  const [alpha, setAlpha] = useState('0.05')
  const [result, setResult] = useState<any>(null)
  const [ci, setCi] = useState<any>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [cols, desc, insightData] = await Promise.all([
  api.columns(dataset.id, versionId),
  api.descriptive(dataset.id, versionId),
  api.insights(dataset.id, versionId),
])
        if (cancelled) return
        setColumns(cols.column_groups)
        setDescriptive(desc)
        setInsights(insightData)
        setX(cols.column_groups.numeric[0] ?? '')
        setY(cols.column_groups.numeric[1] ?? '')
        setGroupColumn(cols.column_groups.categorical[0] ?? '')
      } catch (err) { if (!cancelled) setError(err) }
    })()
    return () => { cancelled = true }
  }, [dataset.id, versionId])

  async function run() {
    setBusy(true); setError(null); setResult(null)
    try {
      const payload: any = { test, alpha: Number(alpha), version_id: versionId }
      if (['pearson', 'spearman', 'ttest_rel', 'chi_square'].includes(test)) { payload.x = x; payload.y = y }
      if (test === 'ttest_ind') {
        payload.x = x; payload.group_column = groupColumn
        payload.group_a = groupA; payload.group_b = groupB
      }
      if (test === 'ttest_1samp') { payload.x = x; payload.popmean = Number(popmean) }
      if (test === 'anova') { payload.x = x; payload.group_column = groupColumn; payload.all_groups = true }
      setResult(await api.runTest(dataset.id, payload))
    } catch (err) { setError(err) } finally { setBusy(false) }
  }

  async function runCi() {
    setBusy(true); setError(null); setCi(null)
    try { setCi(await api.confidenceInterval(dataset.id, x, 0.95)) }
    catch (err) { setError(err) } finally { setBusy(false) }
  }

  if (!columns) return <div className="flex items-center gap-3 py-16 text-sm text-slate-400"><Spinner /> Loading…</div>

  const numeric: string[] = columns.numeric
  const categorical: string[] = [...columns.categorical, ...columns.text]
  const spec = TESTS.find((t) => t.value === test)!

  return (
    <div className="space-y-6">
      {error && <ErrorNote error={error} />}
<Panel
  title="Automatic Key Insights"
  subtitle="AI-free analysis of important patterns and data quality findings"
  actions={
    <Badge tone="good">
      {insights?.overview?.insight_count ?? 0} findings
    </Badge>
  }
>
  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-5">
    {[
      { label: 'Total records', value: insights?.overview?.rows ?? 0 },
      { label: 'Total columns', value: insights?.overview?.columns ?? 0 },
      { label: 'Missing cells', value: insights?.overview?.missing_cells ?? 0 },
      { label: 'Duplicate rows', value: insights?.overview?.duplicate_rows ?? 0 },
    ].map((item) => (
      <div key={item.label} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
        <p className="text-xs text-slate-400">{item.label}</p>
        <p className="mt-1 text-xl font-semibold text-white">
          {Number(item.value).toLocaleString()}
        </p>
      </div>
    ))}
  </div>

  {insights?.insights?.length > 0 ? (
    <div className="space-y-3">
      {insights.insights.map((item: any) => (
        <div key={item.id} className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold text-slate-100">{item.title}</h3>
            <Badge tone={
             item.severity === 'high'
                 ? 'bad'
                : item.severity === 'medium'
                  ? 'warn'
                  : 'neutral'
            }>
              {item.severity}
            </Badge>
          </div>

          <p className="mt-2 text-sm text-slate-300">{item.description}</p>

          {item.metric && (
            <p className="mt-2 text-xs font-medium text-cyan-300">{item.metric}</p>
          )}

          <div className="mt-3 rounded-lg bg-white/[0.04] p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Recommendation
            </p>
            <p className="mt-1 text-sm text-slate-200">{item.recommendation}</p>
          </div>
        </div>
      ))}
    </div>
  ) : (
    <EmptyState
      title="No major issues detected"
      description="The automatic scan did not identify notable patterns or data quality concerns."
    />
  )}
</Panel>
      <Panel title="Descriptive statistics" subtitle={descriptive?.note ?? 'Computed with pandas'}>
        {descriptive?.rows?.length ? (
          <div className="overflow-auto" style={{ maxHeight: 320 }}>
            <table className="min-w-full">
              <thead className="sticky top-0 bg-navy-900">
                <tr>{Object.keys(descriptive.rows[0]).map((h) => <th key={h} className="th">{h}</th>)}</tr>
              </thead>
              <tbody>
                {descriptive.rows.map((row: any, i: number) => (
                  <tr key={i}>
                    {Object.keys(descriptive.rows[0]).map((k) => (
                      <td key={k} className={typeof row[k] === 'number' ? 'td num' : 'td'}>
                        {typeof row[k] === 'number' ? formatNumber(row[k], 4) : String(row[k] ?? '—')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <EmptyState title="No numeric columns" />}
      </Panel>

      <Panel title="Run a statistical test" subtitle="Assumptions and limitations are returned with every result">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="sm:col-span-2 lg:col-span-1">
            <label className="label" htmlFor="test-type">Test</label>
            <select id="test-type" className="select" value={test} onChange={(e) => { setTest(e.target.value); setResult(null) }}>
              {TESTS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>

          {spec.needs.includes('x') && (
            <div>
              <label className="label" htmlFor="test-x">{test === 'anova' || test === 'ttest_ind' ? 'Numeric column' : 'Column X'}</label>
              <select id="test-x" className="select" value={x} onChange={(e) => setX(e.target.value)}>
                {[...numeric, ...categorical].map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          )}

          {['pearson', 'spearman', 'ttest_rel', 'chi_square'].includes(test) && (
            <div>
              <label className="label" htmlFor="test-y">{test === 'chi_square' ? 'Categorical column B' : 'Column Y'}</label>
              <select id="test-y" className="select" value={y} onChange={(e) => setY(e.target.value)}>
                {(test === 'chi_square' ? categorical : numeric).map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          )}

          {spec.needs.includes('group_column') && (
            <div>
              <label className="label" htmlFor="test-group">Group column</label>
              <select id="test-group" className="select" value={groupColumn} onChange={(e) => setGroupColumn(e.target.value)}>
                {categorical.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          )}

          {test === 'ttest_ind' && (
            <>
              <div>
                <label className="label" htmlFor="ga">Group A</label>
                <input id="ga" className="input" value={groupA} onChange={(e) => setGroupA(e.target.value)} placeholder="e.g. North" />
              </div>
              <div>
                <label className="label" htmlFor="gb">Group B</label>
                <input id="gb" className="input" value={groupB} onChange={(e) => setGroupB(e.target.value)} placeholder="e.g. South" />
              </div>
            </>
          )}

          {test === 'ttest_1samp' && (
            <div>
              <label className="label" htmlFor="popmean">Hypothesised mean</label>
              <input id="popmean" type="number" step="any" className="input" value={popmean} onChange={(e) => setPopmean(e.target.value)} />
            </div>
          )}

          <div>
            <label className="label" htmlFor="alpha">Alpha</label>
            <input id="alpha" type="number" step="0.01" min="0.001" max="0.2" className="input" value={alpha} onChange={(e) => setAlpha(e.target.value)} />
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button className="btn-primary" onClick={run} disabled={busy}>{busy ? <Spinner /> : null} Run test</button>
          <button className="btn-ghost" onClick={runCi} disabled={busy || !x}>95% CI for {x || 'column'}</button>
        </div>
      </Panel>

      {ci && (
        <Panel title={`Confidence interval — ${ci.column ?? x}`} subtitle={ci.interpretation}>
          <KeyValues data={ci} columns={3} skip={['interpretation', 'assumptions', 'limitations']} />
          {ci.limitations && <div className="mt-4"><Bullets items={ci.limitations} tone="warn" /></div>}
        </Panel>
      )}

      {result && (
        <Panel
          title={result.test_label ?? spec.label}
          subtitle={result.interpretation}
          actions={<Badge tone={result.significant ? 'good' : 'neutral'}>{result.significant ? 'significant' : 'not significant'}</Badge>}
        >
          <KeyValues data={result} columns={3} skip={['interpretation', 'assumptions', 'limitations', 'test_label', 'significant', 'groups', 'table']} />
          {result.groups && (
            <div className="mt-4 overflow-auto">
              <table className="min-w-full">
                <thead><tr>{Object.keys(result.groups[0] ?? {}).map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
                <tbody>
                  {result.groups.map((g: any, i: number) => (
                    <tr key={i}>{Object.keys(result.groups[0]).map((k) => (
                      <td key={k} className={typeof g[k] === 'number' ? 'td num' : 'td'}>{typeof g[k] === 'number' ? formatNumber(g[k], 4) : String(g[k] ?? '—')}</td>
                    ))}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {result.assumptions?.length > 0 && (
              <div><p className="label">Assumptions</p><Bullets items={result.assumptions} /></div>
            )}
            {result.limitations?.length > 0 && (
              <div><p className="label">Limitations</p><Bullets items={result.limitations} tone="warn" /></div>
            )}
          </div>
        </Panel>
      )}

      <Alert kind="info">
        Statistics are computed with SciPy on the selected dataset version. p-values below 10⁻⁴ are reported in scientific notation, never rounded to zero.
      </Alert>
    </div>
  )
}
