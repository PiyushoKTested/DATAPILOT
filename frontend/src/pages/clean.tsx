import { useEffect, useState } from 'react'
import { api, formatNumber } from '../lib/api'
import { useDataset } from '../components/shell'
import {
  Alert, Badge, EmptyState, ErrorNote, KeyValues, Panel, Spinner,
} from '../components/ui'

interface Plan {
  missing_values: { column: string; strategy: string; constant_value?: any }[]
  drop_duplicates: boolean
  type_corrections: { column: string; target_type: string }[]
  outliers: { column: string; strategy: string; multiplier: number }[]
  trim_whitespace: boolean
  drop_constant_columns: boolean
  drop_empty_columns: boolean
  label: string
}

const EMPTY_PLAN: Plan = {
  missing_values: [],
  drop_duplicates: false,
  type_corrections: [],
  outliers: [],
  trim_whitespace: false,
  drop_constant_columns: false,
  drop_empty_columns: false,
  label: 'Cleaning step',
}

export function CleanTab() {
  const { dataset, versionId, reload, setVersionId } = useDataset()

  const [recs, setRecs] = useState<any[]>([])
  const [history, setHistory] = useState<any[]>([])
  const [plan, setPlan] = useState<Plan>(EMPTY_PLAN)
  const [preview, setPreview] = useState<any>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [ran, setRan] = useState(false)

  const [downloading, setDownloading] = useState(false)

async function downloadPdf() {
  try {
    setDownloading(true)
    setError(null)

    const blob = await api.downloadCleaningReport(dataset.id, versionId)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')

    link.href = url
    link.download = `DATAPILOT_Cleaning_Report_${dataset.name}.pdf`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (err) {
    setError(err)
  } finally {
    setDownloading(false)
  }
}

  async function load() {
    try {
      const [r, h] = await Promise.all([
        api.cleaningRecommendations(dataset.id, versionId),
        api.cleaningHistory(dataset.id),
      ])
      setRecs(r.recommendations || [])
      setHistory(h || [])
      setError(null)
    } catch (err) {
      setError(err)
    }
  }

  useEffect(() => {
    load()
  }, [dataset.id, versionId])

  // Every plan change invalidates the previous preview.
  function updatePlan(updater: (previous: Plan) => Plan) {
    setPlan(previous => updater(previous))
    setPreview(null)
    setRan(false)
  }

  function addRecommendation(rec: any) {
    updatePlan(p => {
      if (rec.type === 'missing_values') {
        if (p.missing_values.some(m => m.column === rec.column)) return p
        return {
          ...p,
          missing_values: [
            ...p.missing_values,
            { column: rec.column, strategy: rec.suggested_strategy || 'median' },
          ],
        }
      }

      if (rec.type === 'duplicates') {
        return { ...p, drop_duplicates: true }
      }

      if (rec.type === 'outliers') {
        if (p.outliers.some(o => o.column === rec.column)) return p
        return {
          ...p,
          outliers: [
            ...p.outliers,
            { column: rec.column, strategy: 'clip', multiplier: 1.5 },
          ],
        }
      }

      return p
    })
  }

  const actionCount =
    plan.missing_values.length +
    plan.outliers.length +
    plan.type_corrections.length +
    Number(plan.drop_duplicates) +
    Number(plan.trim_whitespace) +
    Number(plan.drop_constant_columns) +
    Number(plan.drop_empty_columns)

  async function runPreview() {
    setBusy(true)
    setError(null)

    try {
      const result = await api.previewCleaning(dataset.id, plan, versionId)
      setPreview(result)
      setRan(true)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  async function apply() {
    if (!ran || actionCount === 0) return

    setBusy(true)
    setError(null)

    try {
      const updated = await api.applyCleaning(dataset.id, plan, versionId)

      setPlan(EMPTY_PLAN)
      setPreview(null)
      setRan(false)

      await reload()

      const versions = updated.versions || []
      const newest = versions[versions.length - 1]

      if (newest) setVersionId(newest.id)
      else if (updated.current_version_id) {
        setVersionId(updated.current_version_id)
      }

      await load()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  async function undo(actionId: number) {
    setBusy(true)
    setError(null)

    try {
      const updated = await api.undoCleaning(dataset.id, actionId)
      await reload()

      if (updated.current_version_id) {
        setVersionId(updated.current_version_id)
      }

      await load()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  function resetPlan() {
    setPlan(EMPTY_PLAN)
    setPreview(null)
    setRan(false)
  }

  if (error && !recs.length) {
    return <ErrorNote error={error} />
  }

  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-white">
            Data Cleaning Studio
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Detect issues, build a cleaning plan and preview changes before applying.
          </p>
        </div>

        <Badge tone="neutral">
          {actionCount} actions selected
        </Badge>
      </div>

      {error && <ErrorNote error={error} />}

      <Alert kind="info">
        Your original dataset is protected. Every successful cleaning operation
        creates a new version that you can switch back to or undo.
      </Alert>

      {/* Overview */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
          <p className="text-xs text-slate-500">Recommendations</p>
          <p className="mt-2 text-2xl font-semibold text-white">
            {recs.length}
          </p>
          <p className="mt-1 text-xs text-slate-500">Detected issues</p>
        </div>

        <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
          <p className="text-xs text-slate-500">Selected actions</p>
          <p className="mt-2 text-2xl font-semibold text-white">
            {actionCount}
          </p>
          <p className="mt-1 text-xs text-slate-500">Ready to preview</p>
        </div>

        <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
          <p className="text-xs text-slate-500">Cleaning history</p>
          <p className="mt-2 text-2xl font-semibold text-white">
            {history.length}
          </p>
          <p className="mt-1 text-xs text-slate-500">Recorded actions</p>
        </div>

        <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
          <p className="text-xs text-slate-500">Current status</p>
          <p className="mt-2 text-lg font-semibold text-white">
            {ran ? 'Preview ready' : 'Not previewed'}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {ran ? 'Review before applying' : 'Awaiting your plan'}
          </p>
        </div>
      </div>

      {/* Main workspace */}
      <div className="grid gap-5 lg:grid-cols-2">

        {/* Recommendations */}
        <Panel
          title="Smart recommendations"
          subtitle="Issues detected in your current dataset version"
        >
          {recs.length === 0 ? (
            <EmptyState
              title="Your dataset looks clean"
              description="No missing values, duplicates or outliers were detected."
            />
          ) : (
            <div className="space-y-3">
              {recs.map((rec, i) => {
                const alreadyAdded =
                  (rec.type === 'missing_values' &&
                    plan.missing_values.some(m => m.column === rec.column)) ||
                  (rec.type === 'outliers' &&
                    plan.outliers.some(o => o.column === rec.column)) ||
                  (rec.type === 'duplicates' && plan.drop_duplicates)

                return (
                  <div
                    key={`${rec.type}-${rec.column || i}`}
                    className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-3"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={rec.severity === 'high' ? 'bad' : 'warn'}>
                          {rec.severity || 'info'}
                        </Badge>
                        <span className="text-xs uppercase tracking-wide text-slate-500">
                          {(rec.type || '').replace(/_/g, ' ')}
                        </span>
                      </div>

                      <button
                        className="btn-ghost btn-sm"
                        disabled={alreadyAdded || busy}
                        onClick={() => addRecommendation(rec)}
                      >
                        {alreadyAdded ? 'Added' : '+ Add'}
                      </button>
                    </div>

                    <p className="mt-2 text-sm text-slate-200">
                      {rec.column && (
                        <span className="font-medium text-white">
                          {rec.column}:{' '}
                        </span>
                      )}
                      {rec.reason}
                    </p>
                  </div>
                )
              })}
            </div>
          )}
        </Panel>

        {/* Cleaning plan */}
        <Panel
          title="Cleaning plan"
          subtitle="Configure exactly what you want to change"
          actions={
            <button className="btn-ghost btn-sm" onClick={resetPlan}>
              Reset all
            </button>
          }
        >
          <div className="space-y-4">

            <div>
              <label className="label" htmlFor="plan-label">
                Version name
              </label>
              <input
                id="plan-label"
                className="input"
                value={plan.label}
                onChange={e =>
                  updatePlan(p => ({ ...p, label: e.target.value }))
                }
                placeholder="Enter cleaning version name"
              />
            </div>

            {/* Missing values */}
            {plan.missing_values.length > 0 && (
              <div className="space-y-2">
                <p className="label">Missing value treatment</p>

                {plan.missing_values.map((step, i) => (
                  <div
                    key={step.column}
                    className="flex flex-wrap items-center gap-2 rounded-lg bg-white/[0.03] p-2"
                  >
                    <span className="min-w-0 flex-1 truncate text-sm text-slate-200">
                      {step.column}
                    </span>

                    <select
                      className="select w-auto py-1.5 text-xs"
                      value={step.strategy}
                      onChange={e =>
                        updatePlan(p => ({
                          ...p,
                          missing_values: p.missing_values.map((m, j) =>
                            j === i ? { ...m, strategy: e.target.value } : m
                          ),
                        }))
                      }
                    >
                      {['median', 'mean', 'mode', 'drop_rows', 'constant'].map(s => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>

                    <button
                      className="btn-ghost btn-sm"
                      onClick={() =>
                        updatePlan(p => ({
                          ...p,
                          missing_values: p.missing_values.filter(
                            m => m.column !== step.column
                          ),
                        }))
                      }
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Outliers */}
            {plan.outliers.length > 0 && (
              <div className="space-y-2">
                <p className="label">Outlier treatment</p>

                {plan.outliers.map((step, i) => (
                  <div
                    key={step.column}
                    className="flex flex-wrap items-center gap-2 rounded-lg bg-white/[0.03] p-2"
                  >
                    <span className="min-w-0 flex-1 truncate text-sm text-slate-200">
                      {step.column}
                    </span>

                    <select
                      className="select w-auto py-1.5 text-xs"
                      value={step.strategy}
                      onChange={e =>
                        updatePlan(p => ({
                          ...p,
                          outliers: p.outliers.map((o, j) =>
                            j === i ? { ...o, strategy: e.target.value } : o
                          ),
                        }))
                      }
                    >
                      {['clip', 'remove', 'cap_percentile'].map(s => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>

                    <button
                      className="btn-ghost btn-sm"
                      onClick={() =>
                        updatePlan(p => ({
                          ...p,
                          outliers: p.outliers.filter(
                            o => o.column !== step.column
                          ),
                        }))
                      }
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Other cleaning actions */}
            <div className="space-y-3 border-t border-white/[0.06] pt-4">
              <p className="label">Additional operations</p>

              {([
                ['drop_duplicates', 'Remove duplicate rows'],
                ['trim_whitespace', 'Trim text whitespace'],
                ['drop_constant_columns', 'Remove constant columns'],
                ['drop_empty_columns', 'Remove empty columns'],
              ] as const).map(([key, label]) => (
                <label
                  key={key}
                  className="flex cursor-pointer items-center justify-between gap-3 text-sm text-slate-300"
                >
                  {label}
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-[#3B82F6]"
                    checked={plan[key]}
                    onChange={e =>
                      updatePlan(p => ({ ...p, [key]: e.target.checked }))
                    }
                  />
                </label>
              ))}
            </div>

            {/* Actions */}
            <div className="grid grid-cols-2 gap-2 border-t border-white/[0.06] pt-4">
              <button
                className="btn-ghost"
                onClick={runPreview}
                disabled={busy || actionCount === 0}
              >
                {busy ? <Spinner /> : null}
                Preview changes
              </button>

              <button
                className="btn-primary"
                onClick={apply}
                disabled={busy || actionCount === 0 || !ran}
              >
                {busy ? <Spinner /> : null}
                Apply cleaning
              </button>
            </div>

            {actionCount === 0 && (
              <p className="text-xs text-slate-500">
                Add a recommendation or select a cleaning operation to begin.
              </p>
            )}

            {actionCount > 0 && !ran && (
              <p className="text-xs text-amber-400">
                Preview your changes before applying them.
              </p>
            )}
          </div>
        </Panel>
      </div>

      {/* Preview */}
      {preview && (
        <Panel
          title="Cleaning impact preview"
          subtitle="These changes have not been applied to your dataset"
        >
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="rounded-xl border border-white/[0.07] p-4">
              <p className="mb-3 text-sm font-semibold text-slate-300">
                Before cleaning
              </p>
              <KeyValues
                data={preview.before ?? preview.metrics_before ?? {}}
              />
            </div>

            <div className="rounded-xl border border-white/[0.07] p-4">
              <p className="mb-3 text-sm font-semibold text-slate-300">
                After cleaning
              </p>
              <KeyValues
                data={preview.after ?? preview.metrics_after ?? {}}
              />
            </div>
          </div>
        </Panel>
      )}

      {/* History */}
     <Panel
  title="Cleaning history"
  subtitle="Review previous operations and undo them when needed"
  actions={
    <button
      className="btn-primary btn-sm"
      onClick={downloadPdf}
      disabled={downloading}
    >
      {downloading ? 'Generating PDF...' : '↓ Download PDF'}
    </button>
  }
>
        {history.length === 0 ? (
          <EmptyState
            title="No cleaning history"
            description="Your applied cleaning operations will appear here."
          />
        ) : (
          <div className="divide-y divide-white/[0.06]">
            {history.map(h => (
              <div
                key={h.id}
                className="flex flex-wrap items-center justify-between gap-3 py-4"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-slate-200">
                      {h.summary}
                    </p>

                    {h.is_undone && (
                      <Badge tone="neutral">Undone</Badge>
                    )}
                  </div>

                  <p className="mt-1 text-xs text-slate-500">
                    {new Date(h.created_at).toLocaleString()}
                    {' · '}
                    {h.operation}

                    {h.metrics_before?.rows != null &&
                      h.metrics_after?.rows != null && (
                        <>
                          {' · '}
                          {formatNumber(h.metrics_before.rows, 0)}
                          {' → '}
                          {formatNumber(h.metrics_after.rows, 0)}
                          {' rows'}
                        </>
                      )}
                  </p>
                </div>

                {!h.is_undone && (
                  <button
                    className="btn-ghost btn-sm"
                    onClick={() => undo(h.id)}
                    disabled={busy}
                  >
                    Undo
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}