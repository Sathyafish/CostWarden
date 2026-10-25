import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'

const dashboard = {
  account_id: null,
  kpis: { cost_avoided_monthly: 840.0, cost_avoided_annualized: 10080, cost_avoided_cumulative: 1200, cleanups: 3, open_prs: 1 },
  counts_by_status: { merged: 2, proposed: 1, rejected: 0, failed: 0 },
  by_resource_type: [{ resource_type: 'RdsDbInstance', count: 1, savings: 350.4 }],
  trend: [{ date: '2026-10-01', value: 350.4 }],
  accounts: [{ account_id: '111', name: 'prod', cleanups: 3, cost_avoided_monthly: 840, cost_avoided_cumulative: 1200, open_prs: 1, last_cleanup: '2026-10-20T00:00:00Z' }],
}

const approve = {
  run_id: 'r1', known: true, done: false, findings: { '111': 2 }, errors: {}, outcomes: {}, pr_urls: {}, plans: {},
  pending: {
    type: 'approve_diff', account_id: '111', account_name: 'prod', savings_usd: 260.5, summary: 'Low risk.',
    validation: 'Parsed', unmapped: [], diff: '--- a/main.tf\n+++ b/main.tf\n-  size = 1\n+  count = 0',
    edited: [
      { resource_id: 'vol-1', resource_type: 'EbsVolume', action: 'release', address: 'aws_ebs_volume.a', monthly_savings_usd: 50, severity: 'low' },
      { resource_id: 'i-2', resource_type: 'EC2Instance', action: 'resize', address: 'aws_instance.b', current: 'm5.2xlarge', recommended: 'm5.large', monthly_savings_usd: 210.5, severity: 'medium' },
    ],
  },
}

function route(handlers: Record<string, (init?: RequestInit) => unknown>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const key = Object.keys(handlers).find((k) => url.startsWith(k))
    if (!key) return { ok: false, status: 404, statusText: 'nf', json: async () => ({ detail: `no route ${url}` }) }
    const out = handlers[key](init)
    if (out instanceof Error) return { ok: false, status: 500, statusText: 'err', json: async () => ({ detail: out.message }) }
    return { ok: true, status: 200, statusText: 'ok', json: async () => out }
  }))
}

const base = {
  '/api/info': () => ({ runtime: 'local', store: 'memory', llm: 'fake', demo_seed: true, auth_required: false }),
  '/api/accounts': () => [{ id: '111', name: 'prod', region: 'us-east-1' }],
  '/api/dashboard': () => dashboard,
  '/api/cleanups': () => [{ account_id: '111', run_id: 'a', timestamp: '2026-10-20T00:00:00Z', resources: [{ resource_id: 'db-1' }], monthly_savings_usd: 350.4, pr_url: 'https://github.com/x/y/pull/1', status: 'merged', summary: '' }],
}

describe('app', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('shows the brand and overview KPIs', async () => {
    route(base)
    render(<App />)
    expect(screen.getAllByText(/Warden/)[0]).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Cost avoidance')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByTestId('kpi-Avoided per month')).toHaveTextContent('$840'))
    expect(screen.getByText('Local agents')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /pull\/1/ })).toHaveAttribute('href', 'https://github.com/x/y/pull/1')
  })

  it('shows a retryable error banner when the API is down', async () => {
    route({ '/api/info': () => new Error('x') })
    render(<App />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/no route|Cannot reach|nf/i)
    expect(within(alert).getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('shows an empty-state hint with no cleanups', async () => {
    route({ ...base, '/api/dashboard': () => ({ ...dashboard, kpis: { ...dashboard.kpis, cleanups: 0, cost_avoided_monthly: 0 }, trend: [], by_resource_type: [] }), '/api/cleanups': () => [] })
    render(<App />)
    expect(await screen.findByText(/No cleanups recorded yet/)).toBeInTheDocument()
  })

  it('asks a question and shows a linked answer with its source', async () => {
    route({ ...base, '/api/ask': () => ({ text: 'Last cleanup avoided $350.40. PR: https://github.com/x/y/pull/1.', tool: 'last_cleanup', data: null }) })
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    await user.type(screen.getByLabelText('Question'), 'last cleanup?')
    await user.click(screen.getAllByRole('button', { name: 'Ask' }).at(-1)!)
    expect(await screen.findByText(/Source: last_cleanup/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'https://github.com/x/y/pull/1' })).toBeInTheDocument()
  })

  it('shows an error bubble when asking fails', async () => {
    route({ ...base, '/api/ask': () => new Error('llm down') })
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    await user.type(screen.getByLabelText('Question'), 'hello')
    await user.click(screen.getAllByRole('button', { name: 'Ask' }).at(-1)!)
    expect(await screen.findByText('llm down')).toBeInTheDocument()
  })

  it('walks a run: approve with an exclusion, then confirm the merge', async () => {
    const calls: unknown[] = []
    route({
      ...base,
      '/api/runs/r1/resume': (init) => {
        const v = JSON.parse(String(init?.body)).value
        calls.push(v)
        return v.approved
          ? { ...approve, pending: { type: 'confirm_merge', account_id: '111', pr_url: 'https://github.com/x/y/pull/9' } }
          : { ...approve, pending: null, done: true, outcomes: { '111': 'merged' }, plans: { '111': { ok: true, ran: false, summary: 'plan skipped' } } }
      },
      '/api/runs': () => approve,
    })
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Runs and approvals' }))
    await user.click(screen.getByRole('button', { name: 'Start cleanup run' }))
    expect(await screen.findByText(/Approve changes for prod/)).toBeInTheDocument()
    expect(screen.getByText('Low risk.')).toBeInTheDocument()
    await user.click(screen.getByLabelText('Include i-2'))
    await user.click(screen.getByRole('button', { name: 'Approve and open draft PR' }))
    expect(await screen.findByText(/Confirm the merge for 111/)).toBeInTheDocument()
    expect(calls[0]).toEqual({ approved: true, exclude: ['i-2'] })
    await user.click(screen.getByRole('button', { name: /The PR is merged/ }))
    expect(await screen.findByText(/Run complete/)).toBeInTheDocument()
    expect(calls[1]).toEqual({ merged: true })
    expect(screen.getByText(/plan skipped/)).toBeInTheDocument()
  })

  it('offers retry and skip when a step failed', async () => {
    route({
      ...base,
      '/api/runs': () => ({ ...approve, pending: { type: 'handle_error', account_id: '111', step: 'execute', error: 'plan backend down' } }),
    })
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Runs and approvals' }))
    await user.click(screen.getByRole('button', { name: 'Start cleanup run' }))
    expect(await screen.findByText(/plan backend down/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Skip this account' })).toBeInTheDocument()
  })

  it('disables approval when every resource is excluded', async () => {
    route({ ...base, '/api/runs': () => approve })
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Runs and approvals' }))
    await user.click(screen.getByRole('button', { name: 'Start cleanup run' }))
    await screen.findByText(/Approve changes for prod/)
    await user.click(screen.getByLabelText('Include vol-1'))
    await user.click(screen.getByLabelText('Include i-2'))
    expect(screen.getByRole('button', { name: 'Approve and open draft PR' })).toBeDisabled()
  })
})
