import type { Account, AskAnswer, Cleanup, Dashboard, Info, RunStatus } from './types'

const KEY_URL = 'cw.apiUrl'
const KEY_KEY = 'cw.apiKey'

export interface ApiConfig {
  baseUrl: string
  apiKey: string
}

declare global {
  interface Window {
    /** Written by Terraform into config.js when the app is hosted on S3 + CloudFront. */
    __CW__?: { apiUrl?: string }
  }
}

export function loadConfig(): ApiConfig {
  const env = import.meta.env
  return {
    baseUrl: (localStorage.getItem(KEY_URL) ?? window.__CW__?.apiUrl ?? env.VITE_API_URL ?? '').replace(/\/$/, ''),
    apiKey: localStorage.getItem(KEY_KEY) ?? env.VITE_API_KEY ?? '',
  }
}

export function saveConfig(c: ApiConfig): void {
  localStorage.setItem(KEY_URL, c.baseUrl.trim())
  localStorage.setItem(KEY_KEY, c.apiKey.trim())
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { baseUrl, apiKey } = loadConfig()
  const headers: Record<string, string> = { 'content-type': 'application/json' }
  if (apiKey) headers['x-api-key'] = apiKey
  let res: Response
  try {
    res = await fetch(`${baseUrl}${path}`, { ...init, headers: { ...headers, ...(init.headers as object) } })
  } catch {
    throw new ApiError(0, 'Cannot reach the CostWarden API. Is it running, and is the API URL right?')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* keep statusText */
    }
    if (res.status === 401) detail = 'The API key is missing or wrong. Set it in Settings.'
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

export const api = {
  info: () => request<Info>('/api/info'),
  accounts: () => request<Account[]>('/api/accounts'),
  dashboard: (accountId?: string) =>
    request<Dashboard>(`/api/dashboard${accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''}`),
  cleanups: (accountId?: string, limit = 8) =>
    request<Cleanup[]>(`/api/cleanups?limit=${limit}${accountId ? `&account_id=${encodeURIComponent(accountId)}` : ''}`),
  ask: (question: string) => request<AskAnswer>('/api/ask', post({ question })),
  startRun: (accountIds?: string[]) => request<RunStatus>('/api/runs', post({ account_ids: accountIds ?? null })),
  runStatus: (id: string) => request<RunStatus>(`/api/runs/${encodeURIComponent(id)}`),
  resume: (id: string, value: Record<string, unknown>) =>
    request<RunStatus>(`/api/runs/${encodeURIComponent(id)}/resume`, post({ value })),
  seedDemo: () => request<{ seeded: number }>('/api/demo/seed', post({})),
}
