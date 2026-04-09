// User types
export interface AuthUser {
  id: number
  username: string
  is_admin: boolean
  is_active: boolean
}

export interface AdminUser extends AuthUser {
  created_at?: string
}

// Auth types
export interface LoginCredentials {
  username: string
  password: string
}

export interface LoginResponse {
  token: string
  user: AuthUser
}

// Health types
export interface HealthStatus {
  status: string
  oracle: 'connected' | 'disconnected'
  tinyllama: 'loaded' | 'error'
  phi3: 'loaded' | 'error'
}

// Metadata types
export interface MetadataUser {
  name: string
  actions: number
}

export interface MetadataObject {
  name: string
  actions: number
}

export interface Metadata {
  users: MetadataUser[]
  objects: MetadataObject[]
  db_status: 'connected' | 'disconnected'
}

// Query types
export interface QueryRequest {
  question: string
}

export interface QueryResponse {
  question: string
  sql: string
  synthesis: string
  rows: Record<string, unknown>[]
  row_count: number
  blocked: boolean
  error: string | null
}

export interface QueryProgressStep {
  key: string
  label: string
  summary: string
  status: 'pending' | 'running' | 'completed' | 'error'
  duration_seconds: number | null
}

export interface QueryProgress {
  request_id: string
  status: 'running' | 'completed' | 'error'
  current_step: string | null
  current_summary: string | null
  elapsed_seconds: number
  steps: QueryProgressStep[]
  result: QueryResponse | null
  error: string | null
}

// History types
export interface HistoryEntry {
  id: string
  question: string
  sql: string
  synthesis: string
  rows: Record<string, unknown>[]
  row_count: number
  blocked: boolean
  error: string | null
  created_at: string
  status: 'ok' | 'error'
}

// Settings types
export interface RuntimeSettings {
  oracle_user: string
  oracle_password: string
  oracle_host: string
  oracle_port: number
  oracle_service: string
  oracle_table: string
  interface_lang: 'fr' | 'en'
  max_results: number
  session_duration: number
  logs_retention: number
}

// Audit log types
export interface AuditLogEntry {
  id: number
  user_id: number | null
  username: string | null
  action: string
  details: string | null
  ip_address: string | null
  created_at: string
  success: boolean
}

// Oracle status for UI
export type OracleStatus = 'connected' | 'inactive' | 'disconnected'
