
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, formatBytes, formatNumber, type Project } from '../lib/api'
import {
  Alert, Badge, EmptyState, ErrorNote, Modal, Spinner,
} from '../components/ui'

const THEMES = [
  { bg: 'from-violet-500/20 to-fuchsia-500/10', icon: '✿', color: 'text-violet-300', border: 'border-violet-400/20' },
  { bg: 'from-cyan-500/20 to-blue-500/10', icon: '◈', color: 'text-cyan-300', border: 'border-cyan-400/20' },
  { bg: 'from-orange-500/20 to-pink-500/10', icon: '✳', color: 'text-orange-300', border: 'border-orange-400/20' },
  { bg: 'from-emerald-500/20 to-teal-500/10', icon: '❋', color: 'text-emerald-300', border: 'border-emerald-400/20' },
  { bg: 'from-rose-500/20 to-purple-500/10', icon: '♡', color: 'text-rose-300', border: 'border-rose-400/20' },
  { bg: 'from-amber-500/20 to-yellow-500/10', icon: '✦', color: 'text-amber-300', border: 'border-amber-400/20' },
]

function qualityLabel(score: number | null | undefined) {
  if (score == null) return 'Not scored'
  if (score >= 90) return 'Excellent'
  if (score >= 75) return 'Looking good'
  if (score >= 60) return 'Needs a little love'
  return 'Needs attention'
}

/* --------------------------------------------------------------- projects */

export function Projects() {
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const navigate = useNavigate()

  async function load() {
    try {
      setProjects(await api.listProjects())
      setError(null)
    } catch (err) {
      setError(err)
    }
  }

  useEffect(() => { load() }, [])

  async function create() {
    if (!name.trim()) return
    setBusy(true)
    setFormError(null)
    try {
      const project = await api.createProject(name.trim(), description.trim())
      setOpen(false)
      setName('')
      setDescription('')
      await load()
      navigate(`/projects/${project.id}`)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Could not create project')
    } finally {
      setBusy(false)
    }
  }

  const datasetCount = projects?.reduce((sum, p) => sum + p.datasets.length, 0) ?? 0
  const scored = projects?.flatMap((p) => p.datasets).filter((d) => d.quality_score != null) ?? []
  const avgQuality = scored.length
    ? formatNumber(scored.reduce((sum, d) => sum + (d.quality_score ?? 0), 0) / scored.length, 1)
    : '—'

  const filteredProjects = useMemo(() => {
    if (!projects) return []
    const term = search.trim().toLowerCase()
    if (!term) return projects
    return projects.filter((p) =>
      p.name.toLowerCase().includes(term) ||
      (p.description || '').toLowerCase().includes(term),
    )
  }, [projects, search])

  return (
    <div className="space-y-8">
      {/* Welcome hero */}
      <section className="relative overflow-hidden rounded-[28px] border border-violet-300/15 bg-gradient-to-br from-[#28204A] via-[#211D40] to-[#142B43] p-6 shadow-2xl shadow-violet-950/20 sm:p-9">
        <div className="pointer-events-none absolute -right-16 -top-28 h-80 w-80 rounded-full bg-fuchsia-500/15 blur-[90px]" />
        <div className="pointer-events-none absolute -bottom-32 right-1/3 h-72 w-72 rounded-full bg-cyan-400/10 blur-[90px]" />

        <div className="relative flex flex-col justify-between gap-7 md:flex-row md:items-center">
          <div className="max-w-xl">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-3 py-1.5 text-[10px] font-semibold tracking-wide text-violet-200">
              <span className="text-amber-300">✦</span>
              YOUR CREATIVE DATA SPACE
              <span className="text-emerald-300">●</span>
            </div>
            <h1 className="text-3xl font-black leading-tight tracking-tight text-white sm:text-4xl">
              Your data has a story.
              <br />
              <span className="bg-gradient-to-r from-violet-300 via-pink-300 to-cyan-300 bg-clip-text text-transparent">
                Let's find it. ✨
              </span>
            </h1>
            <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-300/80">
              Organise your datasets, discover hidden patterns and turn messy spreadsheets into meaningful insights.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                className="rounded-xl bg-white px-5 py-3 text-xs font-bold text-[#211D40] shadow-lg shadow-black/10 transition hover:-translate-y-0.5 hover:bg-violet-100"
                onClick={() => setOpen(true)}
              >
                + Create a project
              </button>
              <span className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.05] px-4 py-3 text-xs text-slate-300">
                <span className="text-emerald-300">✦</span>
                Your data, your workspace
              </span>
            </div>
          </div>

          <div className="relative hidden h-44 w-48 shrink-0 items-center justify-center md:flex">
            <div className="absolute h-36 w-36 rounded-full border border-white/10" />
            <div className="absolute h-28 w-28 rounded-full border border-dashed border-violet-300/30" />
            <div className="absolute right-5 top-2 flex h-11 w-11 rotate-12 items-center justify-center rounded-2xl border border-white/15 bg-violet-400/20 text-2xl shadow-xl backdrop-blur">
              ✦
            </div>
            <div className="absolute bottom-3 left-3 flex h-12 w-12 -rotate-12 items-center justify-center rounded-2xl border border-white/15 bg-cyan-400/20 text-2xl shadow-xl backdrop-blur">
              ◈
            </div>
            <div className="flex h-24 w-24 items-center justify-center rounded-[30px] border border-white/20 bg-gradient-to-br from-violet-400/30 to-blue-400/20 text-5xl shadow-2xl shadow-violet-500/20 backdrop-blur-xl">
              ✿
            </div>
            <div className="absolute bottom-1 right-2 rounded-full border border-white/10 bg-[#1A2540] px-3 py-1.5 text-[10px] font-semibold text-cyan-200 shadow-lg">
              Data magic ✨
            </div>
          </div>
        </div>
      </section>

      {error ? <ErrorNote error={error} /> : null}

      {/* Overview cards */}
      <section className="grid gap-3 sm:grid-cols-3">
        <div className="group rounded-2xl border border-violet-400/15 bg-gradient-to-br from-violet-500/[0.12] to-transparent p-5 transition hover:border-violet-400/30">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Your projects</span>
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-400/10 text-lg text-violet-300">▦</span>
          </div>
          <p className="mt-3 text-3xl font-black tracking-tight text-white">{projects?.length ?? '—'}</p>
          <p className="mt-1 text-[11px] text-violet-300/80">Spaces for your ideas</p>
        </div>

        <div className="group rounded-2xl border border-cyan-400/15 bg-gradient-to-br from-cyan-500/[0.10] to-transparent p-5 transition hover:border-cyan-400/30">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Datasets collected</span>
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-400/10 text-lg text-cyan-300">◈</span>
          </div>
          <p className="mt-3 text-3xl font-black tracking-tight text-white">{projects ? datasetCount : '—'}</p>
          <p className="mt-1 text-[11px] text-cyan-300/80">Your data library</p>
        </div>

        <div className="group rounded-2xl border border-emerald-400/15 bg-gradient-to-br from-emerald-500/[0.10] to-transparent p-5 transition hover:border-emerald-400/30">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Average data health</span>
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-400/10 text-lg text-emerald-300">♡</span>
          </div>
          <p className="mt-3 text-3xl font-black tracking-tight text-white">{projects ? avgQuality : '—'}{projects && avgQuality !== '—' ? '%' : ''}</p>
          <p className="mt-1 text-[11px] text-emerald-300/80">Across scored datasets</p>
        </div>
      </section>

      {/* Project collection */}
      <section className="space-y-5">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold tracking-tight text-white">Your little universe</h2>
              <span className="text-lg">🌈</span>
            </div>
            <p className="mt-1 text-xs text-slate-500">All your projects, neatly in one place.</p>
          </div>

          <div className="relative w-full sm:max-w-[260px]">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500">⌕</span>
            <input
              className="w-full rounded-xl border border-white/10 bg-white/[0.04] py-2.5 pl-9 pr-3 text-xs text-white outline-none transition placeholder:text-slate-600 focus:border-violet-400/50 focus:bg-white/[0.06]"
              placeholder="Find a project..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        {!projects && !error && (
          <div className="flex items-center gap-3 py-16 text-sm text-slate-400">
            <Spinner /> Getting your workspace ready...
          </div>
        )}

        {projects?.length === 0 && (
          <div className="rounded-3xl border border-dashed border-violet-300/20 bg-violet-400/[0.03] px-5 py-12 text-center">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-3xl bg-violet-400/10 text-3xl">🪴</div>
            <h3 className="mt-4 text-lg font-bold text-white">A fresh start!</h3>
            <p className="mx-auto mt-2 max-w-sm text-xs leading-relaxed text-slate-400">
              Your workspace is waiting for its first project. Give your ideas a home.
            </p>
            <button className="mt-5 rounded-xl bg-violet-500 px-5 py-2.5 text-xs font-bold text-white transition hover:bg-violet-400" onClick={() => setOpen(true)}>
              Create my first project ✨
            </button>
          </div>
        )}

        {projects && projects.length > 0 && filteredProjects.length === 0 && (
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-10 text-center">
            <div className="text-3xl">🔎</div>
            <p className="mt-3 text-sm font-semibold text-white">No matches found</p>
            <p className="mt-1 text-xs text-slate-500">Try another project name.</p>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filteredProjects.map((project, index) => {
            const theme = THEMES[index % THEMES.length]
            return (
              <Link
                key={project.id}
                to={`/projects/${project.id}`}
                className={`group relative overflow-hidden rounded-2xl border ${theme.border} bg-gradient-to-br ${theme.bg} p-px transition duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-black/20`}
              >
                <div className="h-full rounded-[15px] bg-[#111729]/95 p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className={`flex h-12 w-12 items-center justify-center rounded-2xl border ${theme.border} bg-white/[0.04] text-2xl ${theme.color} transition group-hover:scale-105`}>
                      {theme.icon}
                    </div>
                    <span className="rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-[10px] font-medium text-slate-400">
                      {project.datasets.length} dataset{project.datasets.length === 1 ? '' : 's'}
                    </span>
                  </div>

                  <h3 className="mt-5 truncate text-base font-bold text-white transition group-hover:text-violet-200">
                    {project.name}
                  </h3>
                  <p className="mt-1.5 line-clamp-2 min-h-[36px] text-xs leading-relaxed text-slate-400">
                    {project.description || 'A space for your next data adventure.'}
                  </p>

                  <div className="mt-5 flex items-center justify-between border-t border-white/[0.07] pt-4">
                    <span className="text-[10px] text-slate-500">
                      Updated {new Date(project.updated_at).toLocaleDateString()}
                    </span>
                    <span className={`flex items-center gap-1 text-[11px] font-bold ${theme.color}`}>
                      Open workspace <span className="transition group-hover:translate-x-1">→</span>
                    </span>
                  </div>
                </div>
              </Link>
            )
          })}

          {/* Create project card */}
          {projects && (
            <button
              onClick={() => setOpen(true)}
              className="flex min-h-[215px] flex-col items-center justify-center rounded-2xl border border-dashed border-white/15 bg-white/[0.015] p-6 text-center transition hover:border-violet-400/40 hover:bg-violet-400/[0.04]"
            >
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-violet-400/20 bg-violet-400/10 text-2xl text-violet-300 transition hover:rotate-90">
                +
              </span>
              <span className="mt-4 text-sm font-bold text-slate-200">Something new?</span>
              <span className="mt-1 text-[11px] text-slate-500">Create another project</span>
            </button>
          )}
        </div>
      </section>

      {/* Create project modal */}
      <Modal
        open={open}
        title="Create something awesome ✨"
        onClose={() => setOpen(false)}
        footer={
          <>
            <button className="btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
            <button className="btn-primary" onClick={create} disabled={busy || !name.trim()}>
              {busy ? <Spinner /> : null} Create project
            </button>
          </>
        }
      >
        <div className="space-y-4">
          {formError && <Alert kind="error">{formError}</Alert>}
          <div>
            <label className="label" htmlFor="project-name">Give your project a name</label>
            <input
              id="project-name"
              className="input"
              value={name}
              autoFocus
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. My sales insights ✨"
            />
          </div>
          <div>
            <label className="label" htmlFor="project-desc">What's this project about?</label>
            <textarea
              id="project-desc"
              className="input min-h-[90px]"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="A little description (totally optional)..."
            />
          </div>
          <p className="text-[10px] text-slate-500">Your project is your own little space for datasets and discoveries.</p>
        </div>
      </Modal>
    </div>
  )
}

/* ---------------------------------------------------------- project detail */

export function ProjectDetail() {
  const { projectId } = useParams()
  const id = Number(projectId)
  const [project, setProject] = useState<Project | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  async function load() {
    try {
      const projects = await api.listProjects()
      setProject(projects.find((p) => p.id === id) ?? null)
      setError(null)
    } catch (err) {
      setError(err)
    }
  }

  useEffect(() => { load() }, [id])

  async function onUpload(fileList: FileList | null) {
    const file = fileList?.[0]
    if (!file) return
    setUploading(true)
    setUploadError(null)
    try {
      const dataset = await api.uploadDataset(id, file)
      await load()
      navigate(`/datasets/${dataset.id}`)
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function removeDataset(datasetId: number, name: string) {
    if (!confirm(`Delete dataset "${name}"? All versions and reports will be removed.`)) return
    try {
      await api.deleteDataset(datasetId)
      await load()
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  if (error) return <ErrorNote error={error} />
  if (!project) {
    return <div className="flex items-center gap-3 py-16 text-sm text-slate-400"><Spinner /> Loading your project...</div>
  }

  return (
    <div className="space-y-7">
      <nav className="flex items-center gap-2 text-xs text-slate-500">
        <Link to="/" className="hover:text-violet-300">Projects</Link>
        <span>/</span>
        <span className="text-slate-300">{project.name}</span>
      </nav>

      <section className="relative overflow-hidden rounded-3xl border border-violet-300/15 bg-gradient-to-br from-[#292047] via-[#1C2442] to-[#142D3E] p-6 sm:p-8">
        <div className="pointer-events-none absolute -right-10 -top-20 h-64 w-64 rounded-full bg-violet-500/15 blur-[80px]" />
        <div className="relative">
          <span className="text-xs font-semibold text-violet-200">YOUR PROJECT SPACE ✦</span>
          <h1 className="mt-3 break-words text-3xl font-black tracking-tight text-white">{project.name}</h1>
          <p className="mt-2 text-sm text-slate-300/80">{project.description || 'Your next data adventure starts here.'}</p>
          <div className="mt-5 flex flex-wrap gap-2">
            <span className="rounded-full border border-white/10 bg-white/[0.06] px-3 py-1.5 text-[11px] text-slate-200">
              ◈ {project.datasets.length} datasets
            </span>
            <span className="rounded-full border border-white/10 bg-white/[0.06] px-3 py-1.5 text-[11px] text-slate-200">
              ✦ Your analytics workspace
            </span>
          </div>
        </div>
      </section>

      {/* Upload area */}
      <section
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false)
        }}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          onUpload(e.dataTransfer.files)
        }}
        className={`rounded-3xl border border-dashed p-7 text-center transition sm:p-10 ${
          dragging
            ? 'border-violet-300 bg-violet-400/10'
            : 'border-violet-300/20 bg-gradient-to-br from-violet-500/[0.06] to-cyan-500/[0.03] hover:border-violet-300/40'
        }`}
      >
        <input
          ref={fileRef}
          id="dataset-file"
          type="file"
          className="hidden"
          accept=".csv,.tsv,.xlsx,.xlsm,.json,.jsonl,.ndjson"
          onChange={(e) => onUpload(e.target.files)}
        />
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-3xl border border-violet-300/20 bg-violet-400/10 text-3xl">
          {uploading ? '⏳' : '📂'}
        </div>
        <h2 className="mt-4 text-lg font-bold text-white">
          {uploading ? 'Your data is on its way...' : 'Bring your data to life'}
        </h2>
        <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-slate-400">
          Drop a file here or choose one from your computer. We'll help you explore what's inside.
        </p>
        <button
          className="mt-5 rounded-xl bg-gradient-to-r from-violet-500 to-indigo-500 px-6 py-3 text-xs font-bold text-white shadow-lg shadow-violet-900/25 transition hover:-translate-y-0.5 hover:from-violet-400 hover:to-indigo-400 disabled:opacity-50"
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
        >
          {uploading ? 'Processing file...' : 'Choose a file ↑'}
        </button>
        <p className="mt-3 text-[10px] text-slate-500">CSV · TSV · XLSX · XLSM · JSON · NDJSON · Up to 100 MB</p>
        {uploadError && <div className="mx-auto mt-4 max-w-lg text-left"><Alert kind="error">{uploadError}</Alert></div>}
      </section>

      {/* Dataset list */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-white">Your datasets <span className="text-violet-300">✿</span></h2>
            <p className="mt-1 text-xs text-slate-500">Everything you've brought into this project.</p>
          </div>
          <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[10px] text-slate-400">
            {project.datasets.length} files
          </span>
        </div>

        {project.datasets.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-9 text-center">
            <div className="text-3xl">🧸</div>
            <p className="mt-3 text-sm font-bold text-white">It's a little empty in here</p>
            <p className="mt-1 text-xs text-slate-500">Upload your first dataset and let's make something interesting.</p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {project.datasets.map((dataset, index) => {
              const theme = THEMES[index % THEMES.length]
              return (
                <article key={dataset.id} className="rounded-2xl border border-white/[0.08] bg-[#111729]/90 p-5 transition hover:border-violet-300/25 hover:bg-[#151D32]">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border ${theme.border} bg-gradient-to-br ${theme.bg} text-xl ${theme.color}`}>
                        {theme.icon}
                      </div>
                      <div className="min-w-0">
                        <Link to={`/datasets/${dataset.id}`} className="block truncate text-sm font-bold text-white hover:text-violet-300">
                          {dataset.name}
                        </Link>
                        <p className="mt-0.5 truncate text-[10px] text-slate-500">{dataset.original_filename}</p>
                      </div>
                    </div>
                    <Badge tone={dataset.quality_score == null ? 'neutral' : dataset.quality_score >= 80 ? 'good' : dataset.quality_score >= 60 ? 'warn' : 'bad'}>
                      {dataset.quality_score == null ? '—' : `${formatNumber(dataset.quality_score, 1)}%`}
                    </Badge>
                  </div>

                  <p className="mt-3 text-[10px] text-slate-500">
                    {qualityLabel(dataset.quality_score)}
                  </p>

                  <dl className="mt-4 grid grid-cols-2 gap-3 rounded-xl bg-white/[0.025] p-3">
                    <div>
                      <dt className="text-[10px] text-slate-500">Rows</dt>
                      <dd className="mt-1 text-sm font-bold text-slate-200">{dataset.row_count?.toLocaleString() ?? '—'}</dd>
                    </div>
                    <div>
                      <dt className="text-[10px] text-slate-500">Columns</dt>
                      <dd className="mt-1 text-sm font-bold text-slate-200">{dataset.column_count ?? '—'}</dd>
                    </div>
                    <div>
                      <dt className="text-[10px] text-slate-500">File size</dt>
                      <dd className="mt-1 text-xs font-semibold text-slate-300">{formatBytes(dataset.file_size_bytes)}</dd>
                    </div>
                    <div>
                      <dt className="text-[10px] text-slate-500">Versions</dt>
                      <dd className="mt-1 text-xs font-semibold text-slate-300">{dataset.version_count}</dd>
                    </div>
                  </dl>

                  <div className="mt-4 flex items-center gap-2">
                    <Link to={`/datasets/${dataset.id}`} className="flex-1 rounded-xl bg-violet-500/15 px-3 py-2.5 text-center text-[11px] font-bold text-violet-200 transition hover:bg-violet-500/25">
                      Open dataset →
                    </Link>
                    <a className="rounded-xl border border-white/10 px-3 py-2.5 text-[11px] text-slate-300 transition hover:bg-white/[0.06]" href={api.downloadCsvUrl(dataset.id)} download>
                      ↓ Export
                    </a>
                    <button className="rounded-xl border border-rose-400/10 px-3 py-2.5 text-[11px] text-rose-300 transition hover:bg-rose-500/10" onClick={() => removeDataset(dataset.id, dataset.name)}>
                      Delete
                    </button>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
