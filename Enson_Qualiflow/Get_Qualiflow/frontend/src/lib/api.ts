import type {
  AnalysisDetail,
  AnalysisListItem,
  ExtractedItem,
  ExtractionResponse,
  HealthResponse,
  MeResponse,
  MechanicalProperties,
  TokenResponse,
  ValidationResult,
} from '../types/qualiflow'

const DEFAULT_BASE_URL = 'http://127.0.0.1:8000'
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || DEFAULT_BASE_URL

export class ApiError extends Error {
  status: number

  constructor(message: string, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const TOKEN_KEY = 'qualiflow_access_token'

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setStoredToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearStoredToken() {
  localStorage.removeItem(TOKEN_KEY)
}

function asObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }
  return value as Record<string, unknown>
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && !Number.isNaN(value) ? value : null
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function parseMechanicalProperties(value: unknown): MechanicalProperties | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  const source = asObject(value)
  return {
    yield_strength_mpa: asNumber(source.yield_strength_mpa),
    tensile_strength_mpa: asNumber(source.tensile_strength_mpa),
    elongation_percentage: asNumber(source.elongation_percentage),
  }
}

function parseValidation(value: unknown): ValidationResult | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  const source = asObject(value)
  const deviationsRaw = source.deviations
  const deviations = Array.isArray(deviationsRaw)
    ? deviationsRaw.filter((entry): entry is string => typeof entry === 'string')
    : []

  return {
    is_compliant: asBoolean(source.is_compliant) ?? false,
    deviations,
  }
}

function parseItem(value: unknown): ExtractedItem {
  const source = asObject(value)
  return {
    item_id: asString(source.item_id),
    heat_number: asString(source.heat_number),
    grade: asString(source.grade),
    weight_or_length: asString(source.weight_or_length),
    mechanical_properties: parseMechanicalProperties(source.mechanical_properties),
    validation: parseValidation(source.validation),
    row_confidence: asNumber(source.row_confidence),
    needs_review: asBoolean(source.needs_review) ?? false,
  }
}

function parseExtractionResponse(value: unknown): ExtractionResponse {
  const source = asObject(value)
  const itemsRaw = Array.isArray(source.items) ? source.items : []
  const items = itemsRaw.map(parseItem)

  return {
    supplier_name: asString(source.supplier_name) ?? 'Unknown supplier',
    document_type: asString(source.document_type) ?? 'Unknown document',
    certificate_date: asString(source.certificate_date),
    total_items_detected:
      asNumber(source.total_items_detected) ?? items.length,
    items,
    confidence_score: asNumber(source.confidence_score) ?? 0,
    ai_analysis_remarks: asString(source.ai_analysis_remarks),
    is_compliant: asBoolean(source.is_compliant),
    needs_review: asBoolean(source.needs_review) ?? false,
    review_reasons: Array.isArray(source.review_reasons)
      ? source.review_reasons.filter((x): x is string => typeof x === 'string')
      : [],
  }
}

function mapStatusToMessage(status: number, serverDetail?: string): string {
  if (status === 401) return serverDetail || 'Session expired. Please login again.'
  if (status === 409) return serverDetail || 'This email is already registered.'
  if (status === 415) return serverDetail || 'Only PDF files are accepted.'
  if (status === 422) return serverDetail || 'The PDF could not be processed. Verify the file and retry.'
  if (status === 502) return serverDetail || 'The extraction engine returned an upstream error. Please retry shortly.'
  if (status === 500) return serverDetail || 'Backend internal error occurred during extraction.'
  if (status === 0) {
    return 'Backend is offline or misconfigured. Start FastAPI server and verify ANTHROPIC_API_KEY.'
  }
  return serverDetail || `Request failed with status ${status}.`
}

async function readErrorMessage(response: Response): Promise<string | undefined> {
  try {
    const payload = (await response.json()) as { detail?: unknown }
    if (typeof payload.detail === 'string') {
      return payload.detail
    }
  } catch {
    // ignore parsing failures and fallback to status message
  }
  return undefined
}

async function requestJson<T>(path: string, init?: RequestInit, auth = false): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set('Accept', 'application/json')
  if (auth) {
    const token = getStoredToken()
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
    })
  } catch {
    throw new ApiError(mapStatusToMessage(0), 0)
  }

  if (!response.ok) {
    const detail = await readErrorMessage(response)
    throw new ApiError(mapStatusToMessage(response.status, detail), response.status)
  }

  return (await response.json()) as T
}

export async function getHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>('/health', { method: 'GET' })
}

export async function extractDocument(file: File, auth = false): Promise<ExtractionResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const headers = new Headers()
  if (auth) {
    const token = getStoredToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/extract`, {
      method: 'POST',
      body: formData,
      headers,
    })
  } catch {
    throw new ApiError(mapStatusToMessage(0), 0)
  }

  if (!response.ok) {
    const detail = await readErrorMessage(response)
    throw new ApiError(mapStatusToMessage(response.status, detail), response.status)
  }

  const data = await response.json()
  return parseExtractionResponse(data)
}

export async function register(email: string, password: string): Promise<TokenResponse> {
  return requestJson<TokenResponse>(
    '/api/v1/auth/register',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    },
    false,
  )
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  return requestJson<TokenResponse>(
    '/api/v1/auth/login',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    },
    false,
  )
}

export async function getMe(): Promise<MeResponse> {
  return requestJson<MeResponse>('/api/v1/auth/me', { method: 'GET' }, true)
}

export async function getAnalyses(): Promise<AnalysisListItem[]> {
  return requestJson<AnalysisListItem[]>('/api/v1/analyses', { method: 'GET' }, true)
}

export async function getAnalysisById(id: number): Promise<AnalysisDetail> {
  const raw = await requestJson<AnalysisDetail>(`/api/v1/analyses/${id}`, { method: 'GET' }, true)
  return {
    ...raw,
    extraction: raw.extraction ? parseExtractionResponse(raw.extraction) : null,
  }
}

export async function downloadDocument(documentId: number): Promise<Blob> {
  const token = getStoredToken()
  const headers = new Headers()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${API_BASE_URL}/api/v1/documents/${documentId}/download`, {
    method: 'GET',
    headers,
  })
  if (!response.ok) {
    const detail = await readErrorMessage(response)
    throw new ApiError(mapStatusToMessage(response.status, detail), response.status)
  }
  return response.blob()
}
