import type { ReactNode } from 'react'
import { formatNumber } from '../lib/api'

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <span
      className="inline-block animate-spin rounded-full border-2 border-white/15 border-t-accent"
      style={{ width: size, height: size }}
      role="status"
      aria-label="Loading"
    />
  )
}

export function FullPageSpinner({ label }: { label?: string }) {
  return (
    <div className="grid-noise flex min-h-screen flex-col items-center justify-center gap-4">
      <div className="flex items-center gap-3 text-slate-300">
        <Spinner size={22} />
        <span className="text-sm">{label ?? 'Loading…'}</span>
      </div>
    </div>
  )
}

export function Panel({
  title,
  subtitle,
  actions,
  className = '',
  children,
}: {
  title?: string
  subtitle?: string
  actions?: ReactNode
  className?: string
  children: ReactNode
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-white/[0.06] px-5 py-4">
          <div>
            {title && <h2 className="text-sm font-semibold text-white">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  )
}

export function KpiCard({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string
  value: string | number
  hint?: string
  tone?: 'default' | 'good' | 'warn' | 'bad'
}) {
  const toneClass =
    tone === 'good'
      ? 'text-emerald-300'
      : tone === 'warn'
        ? 'text-amber-300'
        : tone === 'bad'
          ? 'text-red-300'
          : 'text-white'
  return (
    <div className="card card-pad animate-fade-up">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
        {label}
      </p>
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  )
}

export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode
  tone?: 'neutral' | 'accent' | 'violet' | 'good' | 'warn' | 'bad'
}) {
  const map: Record<string, string> = {
    neutral: 'bg-white/[0.07] text-slate-300',
    accent: 'bg-accent/15 text-accent-soft',
    violet: 'bg-accent-violet/15 text-violet-300',
    good: 'bg-emerald-500/15 text-emerald-300',
    warn: 'bg-amber-500/15 text-amber-300',
    bad: 'bg-red-500/15 text-red-300',
  }
  return <span className={`badge ${map[tone]}`}>{children}</span>
}

export function Alert({
  kind = 'error',
  children,
}: {
  kind?: 'error' | 'info' | 'success' | 'warn'
  children: ReactNode
}) {
  const map: Record<string, string> = {
    error: 'border-red-500/25 bg-red-500/10 text-red-200',
    info: 'border-accent/25 bg-accent/10 text-blue-200',
    success: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-200',
    warn: 'border-amber-500/25 bg-amber-500/10 text-amber-200',
  }
  return (
    <div className={`rounded-lg border px-3.5 py-2.5 text-sm ${map[kind]}`} role="alert">
      {children}
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-white/10 bg-white/[0.02] px-6 py-14 text-center">
      <p className="text-sm font-medium text-slate-200">{title}</p>
      {description && <p className="max-w-md text-xs text-slate-400">{description}</p>}
      {action}
    </div>
  )
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null
  const message = error instanceof Error ? error.message : String(error)
  return <Alert kind="error">{message}</Alert>
}

export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
}) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-navy-950/80 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="card relative w-full max-w-lg animate-fade-up">
        <header className="flex items-center justify-between border-b border-white/[0.06] px-5 py-4">
          <h2 className="text-sm font-semibold text-white">{title}</h2>
          <button className="btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="p-5">{children}</div>
        {footer && (
          <footer className="flex justify-end gap-2 border-t border-white/[0.06] px-5 py-3.5">
            {footer}
          </footer>
        )}
      </div>
    </div>
  )
}

export function DataTable({
  columns,
  rows,
  maxHeight = 460,
}: {
  columns: string[]
  rows: Record<string, any>[]
  maxHeight?: number
}) {
  if (!rows.length) return <EmptyState title="No rows to display" />
  const numeric = new Set(
    columns.filter((c) => rows.some((r) => typeof r[c] === 'number')),
  )
  return (
    <div className="overflow-auto rounded-lg border border-white/[0.06]" style={{ maxHeight }}>
      <table className="min-w-full">
        <thead className="sticky top-0 z-10 bg-navy-900">
          <tr>
            {columns.map((c) => (
              <th key={c} className={numeric.has(c) ? 'th text-right' : 'th'}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="hover:bg-white/[0.03]">
              {columns.map((c) => {
                const raw = row[c]
                const text =
                  raw === null || raw === undefined || raw === ''
                    ? '—'
                    : typeof raw === 'number'
                      ? formatNumber(raw, 4)
                      : typeof raw === 'object'
                        ? JSON.stringify(raw)
                        : String(raw)
                return (
                  <td
                    key={c}
                    className={numeric.has(c) ? 'td num text-right' : 'td'}
                    title={text}
                  >
                    {text}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Renders an arbitrary JSON object as a readable definition list. */
export function KeyValues({
  data,
  columns = 2,
  skip = [],
}: {
  data: Record<string, any>
  columns?: number
  skip?: string[]
}) {
  const entries = Object.entries(data).filter(
    ([k, v]) => !skip.includes(k) && v !== null && v !== undefined && typeof v !== 'object',
  )
  if (!entries.length) return null
  return (
    <dl className={`grid gap-x-6 gap-y-2.5 sm:grid-cols-${columns}`}>
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-baseline justify-between gap-3 border-b border-white/[0.04] pb-1.5">
          <dt className="text-xs text-slate-400">
            {key.replace(/_/g, ' ')}
          </dt>
          <dd className="num text-right text-[13px] font-medium text-slate-100">
            {typeof value === 'number' ? formatNumber(value, 6) : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export function Bullets({ items, tone = 'neutral' }: { items: string[]; tone?: 'neutral' | 'warn' }) {
  if (!items?.length) return null
  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 text-[13px] leading-relaxed text-slate-300">
          <span className={tone === 'warn' ? 'text-amber-400' : 'text-accent'}>•</span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}
