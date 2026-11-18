/**
 * Typed API client for the DATAPILOT backend.
 *
 * All requests go through `request()`, which handles the bearer token, JSON
 * decoding and error normalisation. Backend errors are surfaced verbatim from
 * FastAPI's `detail` field so the UI never shows a fabricated message.
 */

const TOKEN_KEY = 'datapilot_token'
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { raw?: boolean } = {},
): Promise<T> {
  const headers = new Headers(options.headers || {})
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

 const response = await fetch(`${API_BASE_URL}/api${path}`, { ...options, headers })

  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) {
        detail = body.detail
          .map((d: any) => `${d.loc?.join('.') ?? ''}: ${d.msg ?? ''}`)
          .join('; ')
      }
    } catch {
      /* keep the generic message */
    }
    if (response.status === 401 && !path.startsWith('/auth/')) {
      setToken(null)
      window.location.href = '/login'
    }
    throw new ApiError(detail, response.status)
  }

  if (response.status === 204) return undefined as T
  if (options.raw) return response as unknown as T
  return (await response.json()) as T
}

/* ------------------------------------------------------------------ types */
export interface User {
  id: number
  email: string
  full_name: string
  created_at: string
  last_login_at: string | null
}

export interface DatasetSummary {
  id: number
  uid: string
  name: string
  original_filename: string
  source_format: string
  file_size_bytes: number
  row_count: number | null
  column_count: number | null
  quality_score: number | null
  version_count: number
  created_at: string
}

export interface Project {
  id: number
  uid: string
  name: string
  description: string
  created_at: string
  updated_at: string
  datasets: DatasetSummary[]
}

export interface Version {
  id: number
  version_number: number
  label: string
  row_count: number
  column_count: number
  column_names: string[]
  dtypes: Record<string, string>
  quality_score: number | null
  is_original: boolean
  parent_version_id: number | null
  created_at: string
}

export interface Dataset {
  id: number
  uid: string
  project_id: number
  name: string
  original_filename: string
  source_format: string
  file_size_bytes: number
  current_version_id: number | null
  created_at: string
  updated_at: string
  versions: Version[]
}

export interface ColumnProfile {
  name: string
  kind: 'numeric' | 'categorical' | 'datetime' | 'text' | 'boolean'
  pandas_dtype: string
  count: number
  non_null: number
  missing: number
  missing_pct: number
  unique: number
  unique_pct: number
  memory_bytes: number
  stats?: Record<string, any>
  frequency?: { value: string; count: number; percentage: number }[]
  sample_values: any[]
}

export interface Quality {
  score: number
  grade: string
  components: Record<string, number>
  weights: Record<string, number>
  methodology: string
  counts: Record<string, number>
  issues: string[]
}

export interface ProfileResponse {
  dataset_id: number
  dataset_name: string
  version_id: number
  version_number: number
  version_label: string
  profile: {
    shape: { rows: number; columns: number }
    column_kinds: Record<string, string>
    column_groups: {
      numeric: string[]
      categorical: string[]
      datetime: string[]
      text: string[]
    }
    columns: ColumnProfile[]
    quality: Quality
    duplicates: { duplicate_rows: number; duplicate_pct: number }
    missing_by_column: { column: string; missing: number; pct: number }[]
    missing_total: number
    memory_bytes: number
  }
  findings: string[]
  numeric_summary: Record<string, any>[]
  recommendations: Record<string, any>[]
}

export interface ChartPayload {
  chart_type: string
  title: string
  x_label?: string
  y_label?: string
  data?: { label: string; value: number }[]
  series?: any[]
  columns?: string[]
  matrix?: Record<string, Record<string, number>>
  stats?: Record<string, any>
  note?: string
  [key: string]: any
}

export interface QueryResponse {
  answer: string
  engine: 'llm' | 'rule_based'
  engine_label: string
  intent: string
  operation: Record<string, any>
  result: Record<string, any>
  explanation: string
  conversation_id: number
  message_id: number
  supported_examples: string[]
  warnings: string[]
  chart?: ChartPayload | null
}

export interface LlmStatus {
  enabled: boolean
  available: boolean
  base_url: string
  model: string
  models: string[]
  message: string
}

/* ------------------------------------------------------------------- api */
export const api = {
  // auth
  signup: (email: string, full_name: string, password: string) =>
    request<{ access_token: string; user: User }>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, full_name, password }),
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string; user: User }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>('/auth/me'),

  // health / llm
  health: () => request<any>('/health'),
  llmStatus: () => request<LlmStatus>('/llm/status'),

  // projects
  listProjects: () => request<Project[]>('/projects'),
  createProject: (name: string, description = '') =>
    request<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify({ name, description }),
    }),
  updateProject: (id: number, data: { name?: string; description?: string }) =>
    request<Project>(`/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteProject: (id: number) =>
    request<void>(`/projects/${id}`, { method: 'DELETE' }),

  // datasets
  listDatasets: (projectId?: number) =>
    request<Dataset[]>(
      `/datasets${projectId ? `?project_id=${projectId}` : ''}`,
    ),
  getDataset: (id: number) => request<Dataset>(`/datasets/${id}`),
  uploadDataset: (projectId: number, file: File, name = '') => {
    const form = new FormData()
    form.append('project_id', String(projectId))
    form.append('name', name)
    form.append('file', file)
    return request<Dataset>('/datasets/upload', { method: 'POST', body: form })
  },
  deleteDataset: (id: number) =>
    request<void>(`/datasets/${id}`, { method: 'DELETE' }),
  renameDataset: (id: number, name: string) =>
    request<Dataset>(`/datasets/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),
  preview: (id: number, versionId?: number, limit = 50) =>
    request<{
      columns: string[]
      rows: Record<string, any>[]
      total_rows: number
      returned_rows: number
      truncated: boolean
      version_id: number
      version_number: number
      version_label: string
    }>(
      `/datasets/${id}/preview?limit=${limit}` +
        (versionId ? `&version_id=${versionId}` : ''),
    ),
  activateVersion: (id: number, versionId: number) =>
    request<Dataset>(`/datasets/${id}/versions/${versionId}/activate`, {
      method: 'POST',
    }),
  downloadCsvUrl: (id: number, versionId?: number) =>
    `/api/datasets/${id}/download${versionId ? `?version_id=${versionId}` : ''}`,

  // profiling
  profile: (id: number, versionId?: number) =>
    request<ProfileResponse>(
      `/datasets/${id}/profile${versionId ? `?version_id=${versionId}` : ''}`,
    ),
  columns: (id: number, versionId?: number) =>
    request<{
      version_id: number
      shape: { rows: number; columns: number }
      columns: {
        name: string
        kind: string
        missing: number
        unique: number
        pandas_dtype: string
      }[]
      column_groups: ProfileResponse['profile']['column_groups']
    }>(`/datasets/${id}/columns${versionId ? `?version_id=${versionId}` : ''}`),

  // cleaning
  cleaningRecommendations: (id: number, versionId?: number) =>
    request<{ version_id: number; recommendations: any[] }>(
      `/datasets/${id}/cleaning/recommendations` +
        (versionId ? `?version_id=${versionId}` : ''),
    ),
  previewCleaning: (id: number, plan: any, versionId?: number) =>
    request<any>(
      `/datasets/${id}/cleaning/preview` +
        (versionId ? `?version_id=${versionId}` : ''),
      { method: 'POST', body: JSON.stringify(plan) },
    ),
  applyCleaning: (id: number, plan: any, versionId?: number) =>
    request<Dataset>(
      `/datasets/${id}/cleaning/apply` +
        (versionId ? `?version_id=${versionId}` : ''),
      { method: 'POST', body: JSON.stringify(plan) },
    ),
  cleaningHistory: (id: number) =>
    request<any[]>(`/datasets/${id}/cleaning/history`),
  undoCleaning: (id: number, actionId: number) =>
    request<Dataset>(`/datasets/${id}/cleaning/undo/${actionId}`, {
      method: 'POST',
    }),

  // charts / stats
  chartSuggestions: (id: number, versionId?: number) =>
    request<{ suggestions: any[] }>(
      `/datasets/${id}/charts/suggestions` +
        (versionId ? `?version_id=${versionId}` : ''),
    ),
  createChart: (id: number, payload: any) =>
    request<ChartPayload>(`/datasets/${id}/charts`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  descriptive: (id: number, versionId?: number) =>
    request<{ rows: any[]; note: string }>(
      `/datasets/${id}/statistics/descriptive` +
        (versionId ? `?version_id=${versionId}` : ''),
    ),
    insights: (id: number, versionId?: number) =>
  request<any>(
    `/datasets/${id}/insights` +
    (versionId ? `?version_id=${versionId}` : "")
  ),
  runTest: (id: number, payload: any) =>
    request<any>(`/datasets/${id}/statistics/test`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  confidenceInterval: (id: number, column: string, confidence = 0.95) =>
    request<any>(`/datasets/${id}/statistics/confidence-interval`, {
      method: 'POST',
      body: JSON.stringify({ column, confidence }),
    }),
  correlations: (id: number, method = 'pearson', columns?: string[]) =>
    request<any>(`/datasets/${id}/statistics/correlations`, {
      method: 'POST',
      body: JSON.stringify({ method, columns }),
    }),
  normality: (id: number, column: string) =>
    request<any>(
      `/datasets/${id}/statistics/normality?column=${encodeURIComponent(column)}`,
    ),
  analysisHistory: (id: number) =>
    request<any[]>(`/datasets/${id}/analysis/history`),

  // NL analyst
  querySuggestions: (id: number, versionId?: number) =>
    request<{ suggestions: string[]; llm: LlmStatus }>(
      `/datasets/${id}/query/suggestions` +
        (versionId ? `?version_id=${versionId}` : ''),
    ),
  ask: (id: number, question: string, conversationId?: number) =>
    request<QueryResponse>(`/datasets/${id}/query`, {
      method: 'POST',
      body: JSON.stringify({
        question,
        conversation_id: conversationId ?? null,
        prefer_llm: true,
      }),
    }),
  conversations: (id: number) =>
    request<any[]>(`/datasets/${id}/conversations`),
  conversation: (conversationId: number) =>
    request<any>(`/conversations/${conversationId}`),

  // reports
  generateReport: (
    id: number,
    fmt: 'pdf' | 'html',
    title: string,
    opts: { charts?: boolean; stats?: boolean; conversation?: boolean } = {},
  ) =>
    request<any>(`/datasets/${id}/reports`, {
      method: 'POST',
      body: JSON.stringify({
        fmt,
        title,
        include_charts: opts.charts ?? true,
        include_statistics: opts.stats ?? true,
        include_conversation: opts.conversation ?? true,
      }),
    }),
  listReports: (id: number) => request<any[]>(`/datasets/${id}/reports`),
 downloadReport: async (uid: string) => {
  const response = await request<Response>(`/reports/${uid}/download`, {
    raw: true,
  })
  return response.blob()
},

  downloadCleaningReport: async (id: number, versionId?: number) => {
    const response = await request<Response>(
      `/datasets/${id}/cleaning/report.pdf` +
        (versionId ? `?version_id=${versionId}` : ''),
      { raw: true },
    )
    return response.blob()
  },
  // dashboard
  dashboard: (id: number, versionId?: number) =>
    request<any>(
      `/datasets/${id}/dashboard${versionId ? `?version_id=${versionId}` : ''}`,
    ),
}

/* --------------------------------------------------------------- helpers */
export function formatNumber(value: any, decimals = 2): string {
  if (value === null || value === undefined || value === '') return 'â€”'
  const num = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(num)) return String(value)
  if (Number.isInteger(num) && Math.abs(num) < 1e15)
    return num.toLocaleString('en-US')
  if (Math.abs(num) >= 1e6 || (Math.abs(num) > 0 && Math.abs(num) < 1e-4))
    return num.toExponential(3)
  return num.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  })
}

export function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${index === 0 ? value : value.toFixed(1)} ${units[index]}`
}


