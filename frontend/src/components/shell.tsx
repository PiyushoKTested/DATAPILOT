
import { createContext, useContext, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate, useParams } from 'react-router-dom'
import { api, type Dataset, type Version } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Badge, ErrorNote, Spinner } from './ui'

/* --------------------------------------------------------------- navigation */

const NAV = [{ to: '/', label: 'Projects', icon: '▦', description: 'Your workspaces' }]

const TABS = [
  { to: '', label: 'Overview', icon: '◈', end: true },
  { to: 'clean', label: 'Data Cleaning', icon: '✦' },
  { to: 'explore', label: 'Explore', icon: '⌁' },
  { to: 'stats', label: 'Statistics', icon: '▥' },
  { to: 'analyst', label: 'Ask DATAPILOT', icon: '✧' },
  { to: 'reports', label: 'Reports', icon: '▤' },
]

/* --------------------------------------------------------------- app layout */

export function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const initials =
    user?.full_name?.trim()?.charAt(0)?.toUpperCase() || 'U'

  return (
    <div className="relative flex min-h-screen overflow-hidden bg-[#080D1B] text-slate-200">
      {/* Ambient background */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -left-40 -top-40 h-96 w-96 rounded-full bg-blue-600/[0.09] blur-[120px]" />
        <div className="absolute right-0 top-1/3 h-96 w-96 rounded-full bg-violet-600/[0.07] blur-[140px]" />
        <div className="absolute bottom-0 left-1/3 h-72 w-72 rounded-full bg-cyan-500/[0.04] blur-[120px]" />
      </div>

      {/* Sidebar */}
      <aside className="relative z-10 hidden h-screen w-[260px] shrink-0 flex-col border-r border-white/[0.07] bg-[#0B1222]/90 backdrop-blur-2xl lg:sticky lg:top-0 lg:flex">
        {/* Brand */}
        <Link to="/" className="flex items-center gap-3 border-b border-white/[0.06] px-6 py-6">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 via-indigo-500 to-violet-600 text-lg font-black text-white shadow-lg shadow-blue-600/25">
            D
          </div>
          <div>
            <p className="text-[17px] font-bold tracking-tight text-white">
              DATAPILOT<span className="text-blue-400">.</span>
            </p>
            <p className="mt-0.5 text-[9px] font-semibold uppercase tracking-[0.2em] text-slate-500">
              Intelligent Analytics
            </p>
          </div>
        </Link>

        {/* Workspace label */}
        <div className="px-5 pb-3 pt-7">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-600">
            Workspace
          </p>
        </div>

        <nav className="flex-1 space-y-2 px-3">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end
              className={({ isActive }) =>
                `group relative flex items-center gap-3 rounded-xl px-3.5 py-3 transition-all duration-200 ${
                  isActive
                    ? 'border border-blue-400/20 bg-gradient-to-r from-blue-500/15 to-violet-500/[0.08] text-white shadow-lg shadow-blue-950/20'
                    : 'border border-transparent text-slate-400 hover:bg-white/[0.04] hover:text-white'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span className="absolute bottom-2 left-0 top-2 w-[3px] rounded-full bg-gradient-to-b from-blue-400 to-violet-500" />
                  )}
                  <span className={`flex h-9 w-9 items-center justify-center rounded-lg text-lg transition ${
                    isActive
                      ? 'bg-blue-500/15 text-blue-300'
                      : 'bg-white/[0.04] text-slate-500 group-hover:text-slate-200'
                  }`}>
                    {item.icon}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold">{item.label}</span>
                    <span className="mt-0.5 block text-[10px] text-slate-500">
                      {item.description}
                    </span>
                  </span>
                  {isActive && <span className="h-1.5 w-1.5 rounded-full bg-blue-400" />}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Local analytics information */}
        <div className="mx-4 mb-4 rounded-2xl border border-blue-400/15 bg-gradient-to-br from-blue-500/[0.10] to-violet-500/[0.06] p-4">
          <div className="mb-2 flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.7)]" />
            <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-300">
              Local processing
            </span>
          </div>
          <p className="text-xs leading-relaxed text-slate-400">
            Your analytics workspace, built for transparent and reliable insights.
          </p>
        </div>

        {/* User profile */}
        <div className="border-t border-white/[0.07] p-4">
          <div className="flex items-center gap-3 rounded-xl p-2">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-blue-600 text-sm font-bold text-white">
              {initials}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-semibold text-white">
                {user?.full_name || 'User'}
              </p>
              <p className="truncate text-[10px] text-slate-500">
                {user?.email}
              </p>
            </div>
          </div>
          <button
            className="mt-2 flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-xs font-medium text-slate-400 transition hover:bg-rose-500/10 hover:text-rose-300"
            onClick={() => {
              logout()
              navigate('/login')
            }}
          >
            <span>↪</span>
            Sign out
          </button>
        </div>
      </aside>

      {/* Main application */}
      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header className="sticky top-0 z-20 flex min-h-[68px] items-center justify-between gap-4 border-b border-white/[0.07] bg-[#0B1222]/80 px-5 backdrop-blur-2xl lg:px-9">
          <Link to="/" className="flex items-center gap-2.5 lg:hidden">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-violet-600 font-bold text-white">
              D
            </span>
            <span className="font-bold text-white">DATAPILOT.</span>
          </Link>

          <div className="hidden items-center gap-2 text-xs text-slate-500 lg:flex">
            <span className="text-blue-400">✦</span>
            <span>Turn raw data into meaningful decisions.</span>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2 rounded-full border border-emerald-400/15 bg-emerald-400/[0.06] px-3 py-1.5 sm:flex">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              <span className="text-[10px] font-medium text-emerald-300">Workspace active</span>
            </div>
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/[0.05] text-xs font-bold text-white">
              {initials}
            </div>
            <span className="hidden max-w-[150px] truncate text-xs font-medium text-slate-300 sm:block">
              {user?.full_name}
            </span>
          </div>
        </header>

        {/* Page content */}
        <main className="mx-auto w-full max-w-[1500px] flex-1 px-5 py-7 lg:px-9 lg:py-9">
          <Outlet />
        </main>

        <footer className="border-t border-white/[0.05] px-6 py-4 text-center text-[10px] text-slate-600">
          DATAPILOT · Intelligent Analytics Workspace
        </footer>
      </div>
    </div>
  )
}

/* --------------------------------------------------------- dataset context */

interface DatasetContextValue {
  dataset: Dataset
  versionId: number | undefined
  setVersionId: (id: number) => void
  version: Version | undefined
  reload: () => Promise<void>
}

const DatasetContext = createContext<DatasetContextValue | null>(null)

export function useDataset(): DatasetContextValue {
  const ctx = useContext(DatasetContext)
  if (!ctx) throw new Error('useDataset must be used inside <DatasetShell>')
  return ctx
}

/* -------------------------------------------------------------- dataset shell */

export function DatasetShell() {
  const { datasetId } = useParams()
  const id = Number(datasetId)
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [versionId, setVersionId] = useState<number | undefined>(undefined)
  const [error, setError] = useState<unknown>(null)

  async function load() {
    try {
      const next = await api.getDataset(id)
      setDataset(next)
      setVersionId((current) =>
        current && next.versions.some((v) => v.id === current)
          ? current
          : (next.current_version_id ?? next.versions[next.versions.length - 1]?.id),
      )
      setError(null)
    } catch (err) {
      setError(err)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  if (error) return <ErrorNote error={error} />

  if (!dataset) {
    return (
      <div className="flex items-center justify-center gap-3 py-24 text-sm text-slate-400">
        <Spinner />
        Loading your dataset...
      </div>
    )
  }

  const version = dataset.versions.find((v) => v.id === versionId)

  return (
    <DatasetContext.Provider value={{ dataset, versionId, setVersionId, version, reload: load }}>
      <div className="space-y-7">
        {/* Breadcrumb */}
        <nav className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <Link to="/" className="transition hover:text-blue-300">Projects</Link>
          <span className="text-slate-700">/</span>
          <Link to={`/projects/${dataset.project_id}`} className="transition hover:text-blue-300">
            Project
          </Link>
          <span className="text-slate-700">/</span>
          <span className="max-w-[220px] truncate font-medium text-slate-300">
            {dataset.name}
          </span>
        </nav>

        {/* Dataset information panel */}
        <section className="relative overflow-hidden rounded-2xl border border-white/[0.09] bg-gradient-to-br from-[#111D35] via-[#10182C] to-[#17142F] p-5 shadow-2xl shadow-black/20 sm:p-7">
          <div className="pointer-events-none absolute -right-16 -top-24 h-64 w-64 rounded-full bg-blue-500/[0.12] blur-[80px]" />
          <div className="pointer-events-none absolute -bottom-24 right-1/3 h-48 w-48 rounded-full bg-violet-500/[0.10] blur-[70px]" />

          <div className="relative flex flex-col justify-between gap-6 xl:flex-row xl:items-center">
            <div className="min-w-0">
              <div className="mb-3 flex items-center gap-2">
                <span className="rounded-lg border border-blue-400/20 bg-blue-400/10 px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.15em] text-blue-300">
                  Active dataset
                </span>
                <Badge tone="neutral">{dataset.source_format.toUpperCase()}</Badge>
              </div>

              <h1 className="break-words text-2xl font-bold tracking-tight text-white sm:text-3xl">
                {dataset.name}
              </h1>

              <p className="mt-2 break-all text-xs text-slate-400">
                {dataset.original_filename}
              </p>

              <div className="mt-5 flex flex-wrap items-center gap-2">
                {version && (
                  <Badge tone={version.is_original ? 'neutral' : 'accent'}>
                    v{version.version_number} · {version.label}
                  </Badge>
                )}
                {version && (
                  <>
                    <span className="rounded-lg border border-white/[0.07] bg-white/[0.04] px-3 py-1.5 text-xs text-slate-300">
                      <strong className="text-white">{version.row_count.toLocaleString()}</strong> rows
                    </span>
                    <span className="rounded-lg border border-white/[0.07] bg-white/[0.04] px-3 py-1.5 text-xs text-slate-300">
                      <strong className="text-white">{version.column_count}</strong> columns
                    </span>
                  </>
                )}
              </div>
            </div>

            <div className="relative flex flex-wrap items-end gap-3">
              <div className="min-w-[170px] flex-1">
                <label className="mb-2 block text-[10px] font-bold uppercase tracking-wider text-slate-500" htmlFor="version-select">
                  Dataset version
                </label>
                <select
                  id="version-select"
                  className="select w-full border-white/10 bg-[#0B1222]/80 py-2.5 text-xs"
                  value={versionId ?? ''}
                  onChange={(e) => setVersionId(Number(e.target.value))}
                >
                  {dataset.versions.map((v) => (
                    <option key={v.id} value={v.id}>
                      v{v.version_number} — {v.label}
                    </option>
                  ))}
                </select>
              </div>

              <a
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-blue-400/20 bg-blue-500/10 px-4 py-2.5 text-xs font-semibold text-blue-200 transition hover:border-blue-400/40 hover:bg-blue-500/20"
                href={api.downloadCsvUrl(dataset.id, versionId)}
                download
              >
                <span>↓</span>
                Export CSV
              </a>
            </div>
          </div>
        </section>

        {/* Dataset navigation */}
        <nav className="flex gap-1 overflow-x-auto border-b border-white/[0.08] pb-px">
          {TABS.map((tab) => (
            <NavLink
              key={tab.label}
              to={tab.to ? `/datasets/${dataset.id}/${tab.to}` : `/datasets/${dataset.id}`}
              end={tab.end}
              className={({ isActive }) =>
                `relative flex shrink-0 items-center gap-2 whitespace-nowrap px-4 py-3 text-xs font-semibold transition-all ${
                  isActive
                    ? 'text-blue-300 after:absolute after:bottom-0 after:left-3 after:right-3 after:h-[2px] after:rounded-full after:bg-gradient-to-r after:from-blue-400 after:to-violet-400'
                    : 'text-slate-500 hover:text-slate-200'
                }`
              }
            >
              <span className="text-sm">{tab.icon}</span>
              {tab.label}
            </NavLink>
          ))}
        </nav>

        <Outlet />
      </div>
    </DatasetContext.Provider>
  )
}
