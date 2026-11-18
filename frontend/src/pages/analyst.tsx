import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api, type LlmStatus, type QueryResponse } from '../lib/api'
import { ChartRenderer } from '../components/chart'
import { useDataset } from '../components/shell'
import { Alert, Badge, ErrorNote, Panel, Spinner } from '../components/ui'

interface Turn {
  question: string
  response?: QueryResponse
  error?: string
}

export function AnalystTab() {
  const { dataset, versionId } = useDataset()
  const [llm, setLlm] = useState<LlmStatus | null>(null)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [turns, setTurns] = useState<Turn[]>([])
  const [question, setQuestion] = useState('')
  const [conversationId, setConversationId] = useState<number | undefined>(undefined)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await api.querySuggestions(dataset.id, versionId)
        if (cancelled) return
        setSuggestions(res.suggestions)
        setLlm(res.llm)
      } catch (err) { if (!cancelled) setError(err) }
    })()
    return () => { cancelled = true }
  }, [dataset.id, versionId])

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [turns])

  async function ask(text: string) {
    const clean = text.trim()
    if (!clean || busy) return
    setBusy(true); setError(null)
    const index = turns.length
    setTurns((prev) => [...prev, { question: clean }])
    setQuestion('')
    try {
      const response = await api.ask(dataset.id, clean, conversationId)
      setConversationId(response.conversation_id)
      setTurns((prev) => prev.map((t, i) => (i === index ? { ...t, response } : t)))
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Query failed'
      setTurns((prev) => prev.map((t, i) => (i === index ? { ...t, error: message } : t)))
    } finally { setBusy(false) }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    ask(question)
  }

  return (
    <div className="space-y-5">
      {error ? <ErrorNote error={error} /> : null}

      <Alert kind={llm?.available ? 'success' : 'info'}>
        {llm?.available ? (
          <>Local LLM detected (<span className="font-medium">{llm.model}</span> at {llm.base_url}). It only chooses which verified operation to run and paraphrases results â€” the rule-based engine computes every number.</>
        ) : (
          <>No local LLM reachable, so the <span className="font-medium">rule-based engine</span> answers every question. All numbers are computed with pandas/NumPy/SciPy â€” nothing is simulated.</>
        )}
      </Alert>

      <Panel
        title="Ask a question about your data"
        subtitle="Answers are computed on this dataset version, then explained"
        actions={turns.length > 0 ? (
          <button className="btn-ghost btn-sm" onClick={() => { setTurns([]); setConversationId(undefined) }}>New conversation</button>
        ) : undefined}
      >
        <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
          {turns.length === 0 && (
            <div className="rounded-lg border border-dashed border-white/10 bg-white/[0.02] p-5">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Try one of these</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {suggestions.map((s) => (
                  <button key={s} className="chip transition hover:border-accent/40 hover:bg-accent/10 hover:text-white" onClick={() => ask(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((turn, i) => (
            <div key={i} className="space-y-2.5">
              <div className="flex justify-end">
                <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-sm text-white">{turn.question}</p>
              </div>

              {!turn.response && !turn.error && (
                <div className="flex items-center gap-2 text-xs text-slate-400"><Spinner /> Computing from the actual dataâ€¦</div>
              )}

              {turn.error && <Alert kind="error">{turn.error}</Alert>}

              {turn.response && (
                <div className="max-w-[92%] space-y-2.5">
                  <div className="rounded-2xl rounded-bl-sm border border-white/[0.08] bg-navy-900/70 px-4 py-3">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <Badge tone={turn.response.engine === 'llm' ? 'violet' : 'accent'}>
                        {turn.response.engine_label}
                      </Badge>
                      <span className="text-[10px] uppercase tracking-wider text-slate-500">
                        {turn.response.intent.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-100">{turn.response.answer}</p>

                    {turn.response.chart && (
                      <div className="mt-4 min-w-0 overflow-hidden rounded-2xl border border-white/[0.08] bg-slate-950/40 p-2 sm:p-3">
                        <h4 className="mb-2 px-2 text-sm font-semibold text-slate-100">
                          {turn.response.chart.title}
                        </h4>
                        <ChartRenderer chart={turn.response.chart} height={260} />
                      </div>
                    )}

                    {turn.response.result && Object.keys(turn.response.result).length > 0 && (
                      <div className="mt-3 border-t border-white/[0.06] pt-2.5">
                        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Verified result</p>
                        <div className="flex flex-wrap gap-1.5">
                          {Object.entries(turn.response.result)
                            .filter(([, v]) => typeof v !== 'object')
                            .slice(0, 8)
                            .map(([k, v]) => (
                              <span key={k} className="chip">
                                <span className="text-slate-500">{k.replace(/_/g, ' ')}</span>
                                <span className="num text-slate-100">{typeof v === 'number' ? v.toLocaleString('en-US', { maximumFractionDigits: 4 }) : String(v)}</span>
                              </span>
                            ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {turn.response.warnings?.length > 0 && (
                    <div className="space-y-1.5">
                      {turn.response.warnings.map((w, j) => <Alert key={j} kind="warn">{w}</Alert>)}
                    </div>
                  )}

                  {turn.response.engine === 'rule_based' && turn.response.supported_examples?.length > 0 && (
                    <details className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
                      <summary className="cursor-pointer text-[11px] text-slate-400">Question formats I understand</summary>
                      <ul className="mt-2 space-y-1">
                        {turn.response.supported_examples.map((s, j) => (
                          <li key={j} className="text-[12px] text-slate-300">â€¢ {s}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )}
            </div>
          ))}
          <div ref={endRef} />
        </div>

        <form onSubmit={onSubmit} className="mt-4 flex gap-2 border-t border-white/[0.06] pt-4">
          <input
            className="input"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. Which region has the highest total revenue?"
            aria-label="Ask a question about your data"
            disabled={busy}
          />
          <button type="submit" className="btn-primary shrink-0" disabled={busy || !question.trim()}>
            {busy ? <Spinner /> : null} Ask
          </button>
        </form>
      </Panel>
    </div>
  )
}

