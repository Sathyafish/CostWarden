export interface Info {
  runtime: string
  store: string
  llm: string
  demo_seed: boolean
  auth_required: boolean
}

export interface AccountRow {
  account_id: string
  name: string
  cleanups: number
  cost_avoided_monthly: number
  cost_avoided_cumulative: number
  open_prs: number
  last_cleanup: string | null
}

export interface Dashboard {
  account_id: string | null
  kpis: {
    cost_avoided_monthly: number
    cost_avoided_annualized: number
    cost_avoided_cumulative: number
    cleanups: number
    open_prs: number
  }
  counts_by_status: Record<string, number>
  by_resource_type: { resource_type: string; count: number; savings: number }[]
  trend: { date: string; value: number }[]
  accounts: AccountRow[]
}

export interface Cleanup {
  account_id: string
  run_id: string
  timestamp: string
  resources: { resource_id?: string; resource_type?: string; monthly_savings_usd?: number }[]
  monthly_savings_usd: number
  pr_url: string | null
  status: string
  summary: string
}

export interface Account {
  id: string
  name: string
  region: string
}

export interface AskAnswer {
  text: string
  tool: string | null
  data: unknown
}

export interface EditedResource {
  resource_id: string
  resource_type: string
  action: string
  address: string
  current?: string | null
  recommended?: string | null
  monthly_savings_usd: number
  severity: string
}

export type Pending =
  | {
      type: 'approve_diff'
      account_id: string
      account_name: string
      diff: string
      savings_usd: number
      edited: EditedResource[]
      unmapped: { finding: { resource_id: string }; reason: string }[]
      summary: string
      validation: string
    }
  | { type: 'confirm_merge'; account_id: string; pr_url: string }
  | { type: 'handle_error'; account_id: string; step: string; error: string }

export interface RunStatus {
  run_id: string
  known: boolean
  done: boolean
  pending: Pending | null
  findings: Record<string, number>
  errors: Record<string, string>
  outcomes: Record<string, string>
  pr_urls: Record<string, string>
  plans: Record<string, { ok: boolean; ran: boolean; summary: string }>
}
