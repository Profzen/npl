import type {
  LoginCredentials,
  LoginResponse,
  AuthUser,
  HealthStatus,
  Metadata,
  QueryRequest,
  QueryProgress,
  QueryResponse,
  HistoryEntry,
  RuntimeSettings,
  AdminUser,
  AuditLogEntry,
} from './types'

const TOKEN_KEY = 'asksmart_token'
const API_BASE = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://127.0.0.1:8000/api'

interface BackendHistoryEntry {
  timestamp?: number
  question: string
  sql: string
  synthesis: string
  row_count: number
  blocked?: boolean
  error?: string | null
}

interface BackendAdminUser {
  id: number
  username: string
  is_admin: boolean
  is_active: boolean
  created_at?: number
}

interface BackendAuditLogEntry {
  id: number
  timestamp: number
  username: string
  action: string
  question: string
  sql_text: string
  result_status: string
  row_count: number
  details: string
}

interface BackendQueryStartResponse {
  request_id: string
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  }

  if (token) {
    ;(headers as Record<string, string>)['X-Auth-Token'] = token
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    })
  } catch {
    throw new ApiError(503, 'Le serveur est inaccessible. Verifiez que le backend est bien demarre.')
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    const detail =
      errorData.detail ||
      (response.status === 500
        ? 'Erreur interne du serveur. Consultez les logs backend.'
        : `Erreur ${response.status}`)
    throw new ApiError(response.status, detail)
  }

  return response.json()
}

export async function login(credentials: LoginCredentials): Promise<LoginResponse> {
  const response = await apiFetch<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })
  setToken(response.token)
  return response
}

export async function getMe(): Promise<AuthUser> {
  return apiFetch<AuthUser>('/auth/me')
}

export async function logout(): Promise<void> {
  try {
    await apiFetch<{ status: string }>('/auth/logout', { method: 'POST' })
  } finally {
    clearToken()
  }
}

export async function getHealth(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>('/health')
}

export async function getMetadata(): Promise<Metadata> {
  return apiFetch<Metadata>('/metadata')
}

export async function submitQuery(request: QueryRequest): Promise<QueryResponse> {
  const payload = await apiFetch<QueryResponse>('/query', {
    method: 'POST',
    body: JSON.stringify(request),
  })

  return {
    ...payload,
    blocked: false,
  }
}

export async function submitTrackedQuery(
  request: QueryRequest,
  onProgress: (progress: QueryProgress) => void
): Promise<QueryResponse> {
  const startPayload = await apiFetch<BackendQueryStartResponse>('/query/start', {
    method: 'POST',
    body: JSON.stringify(request),
  })

  while (true) {
    const progress = await apiFetch<QueryProgress>(`/query/progress/${startPayload.request_id}`)
    onProgress(progress)

    if (progress.status === 'completed') {
      if (!progress.result) {
        throw new ApiError(500, 'La requete est terminee mais aucun resultat n a ete renvoye.')
      }
      return {
        ...progress.result,
        blocked: false,
      }
    }

    if (progress.status === 'error') {
      throw new ApiError(500, progress.error || 'Une erreur est survenue pendant l analyse.')
    }

    await new Promise((resolve) => window.setTimeout(resolve, 500))
  }
}

export async function getHistory(): Promise<HistoryEntry[]> {
  const payload = await apiFetch<BackendHistoryEntry[]>('/history')

  return payload.map((entry, index) => {
    const ts = Number(entry.timestamp || 0)
    const createdAt = ts > 0 ? new Date(ts * 1000).toISOString() : new Date().toISOString()

    return {
      id: `${ts || Date.now()}-${index}`,
      question: entry.question,
      sql: entry.sql,
      synthesis: entry.synthesis,
      rows: [],
      row_count: Number(entry.row_count || 0),
      blocked: false,
      error: entry.error ?? null,
      created_at: createdAt,
      status: entry.error ? 'error' : 'ok',
    }
  })
}

export async function getSettings(): Promise<RuntimeSettings> {
  return apiFetch<RuntimeSettings>('/settings')
}

export async function updateSettings(settings: RuntimeSettings): Promise<RuntimeSettings> {
  return apiFetch<RuntimeSettings>('/settings', {
    method: 'POST',
    body: JSON.stringify(settings),
  })
}

export async function getUsers(): Promise<AdminUser[]> {
  const payload = await apiFetch<BackendAdminUser[]>('/admin/users')
  return payload.map((user) => ({
    ...user,
    created_at: user.created_at ? new Date(user.created_at * 1000).toISOString() : undefined,
  }))
}

export async function createUser(username: string, password: string, is_admin: boolean): Promise<AdminUser> {
  const payload = await apiFetch<BackendAdminUser>('/admin/users', {
    method: 'POST',
    body: JSON.stringify({ username, password, is_admin }),
  })
  return {
    ...payload,
    created_at: payload.created_at ? new Date(payload.created_at * 1000).toISOString() : undefined,
  }
}

export async function updateUserStatus(userId: number, isActive: boolean): Promise<AdminUser> {
  const payload = await apiFetch<BackendAdminUser>(`/admin/users/${userId}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ is_active: isActive }),
  })
  return {
    ...payload,
    created_at: payload.created_at ? new Date(payload.created_at * 1000).toISOString() : undefined,
  }
}

export async function deleteUser(userId: number): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/admin/users/${userId}`, {
    method: 'DELETE',
  })
}

export async function getAuditLogs(limit = 300): Promise<AuditLogEntry[]> {
  const payload = await apiFetch<BackendAuditLogEntry[]>(`/admin/audit-logs?limit=${limit}`)
  return payload.map((log) => ({
    id: log.id,
    user_id: null,
    username: log.username,
    action: log.action,
    details: log.details,
    ip_address: null,
    created_at: new Date(log.timestamp * 1000).toISOString(),
    success: log.result_status === 'ok',
  }))
}
