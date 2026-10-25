import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Linkified, ErrorBanner, Spinner, StatusChip } from '../components/Bits'
import { StatusBars, TrendChart, TypeChart } from '../components/Charts'
import { KpiCard } from '../components/KpiCard'
import { compactMoney, money, shortDate, timeAgo } from '../format'
import type { Account, Cleanup, Dashboard, Info } from '../types'

interface Props {
  info: Info | null
  reloadKey: number
}

export function Overview({ info, reloadKey }: Props) {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [accountId, setAccountId] = useState<string>('')
  const [dash, setDash] = useState<Dashboard | null>(null)
  const [cleanups, setCleanups] = useState<Cleanup[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [a, d, c] = await Promise.all([api.accounts(), api.dashboard(accountId || undefined), api.cleanups(accountId || undefined)])
      setAccounts(a)
      setDash(d)
      setCleanups(c)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [accountId])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  const seed = async () => {
    try {
      await api.seedDemo()
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const k = dash?.kpis
  const empty = k && k.cleanups === 0

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Cost avoidance</h1>
          <p className="muted">Savings from cleanups that were reviewed, approved and merged.</p>
        </div>
        <div className="controls">
          <select value={accountId} onChange={(e) => setAccountId(e.target.value)} aria-label="Account">
            <option value="">All accounts</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({a.id})
              </option>
            ))}
          </select>
          <button className="btn btn-ghost" onClick={() => void load()}>
            Refresh
          </button>
          {info?.demo_seed && (
            <button className="btn btn-ghost" onClick={() => void seed()}>
              Load demo history
            </button>
          )}
        </div>
      </div>

      {error && <ErrorBanner onRetry={() => void load()}>{error}</ErrorBanner>}
      {loading && !dash && <Spinner label="Loading the dashboard" />}

      {k && (
        <>
          <div className="kpi-grid">
            <KpiCard label="Avoided per month" value={k.cost_avoided_monthly} format={(n) => money(n, 0)} hint="Run-rate from merged cleanups" big />
            <KpiCard label="Avoided per year" value={k.cost_avoided_annualized} format={compactMoney} hint="Monthly run-rate x 12" accent="blue" />
            <KpiCard label="Avoided to date" value={k.cost_avoided_cumulative} format={(n) => money(n, 0)} hint="Accumulated since each merge" accent="blue" />
            <KpiCard label="Cleanups" value={k.cleanups} format={(n) => String(Math.round(n))} hint="Across all statuses" accent="amber" />
            <KpiCard label="Open PRs" value={k.open_prs} format={(n) => String(Math.round(n))} hint="Waiting for a merge" accent="amber" />
          </div>

          {empty && (
            <div className="banner banner-info">
              No cleanups recorded yet. Start a run in <strong>Runs and approvals</strong>
              {info?.demo_seed ? ', or load the demo history above.' : '.'}
            </div>
          )}

          <div className="grid-2">
            <div className="card">
              <h2>Run-rate avoided over time</h2>
              <TrendChart data={dash.trend} />
            </div>
            <div className="card">
              <h2>Avoided by resource type</h2>
              <TypeChart data={dash.by_resource_type} />
            </div>
          </div>

          <div className="grid-2">
            <div className="card">
              <h2>Accounts</h2>
              <table className="table">
                <thead>
                  <tr>
                    <th>Account</th>
                    <th className="num">Avoided / mo</th>
                    <th className="num">Cleanups</th>
                    <th className="num">Open PRs</th>
                    <th>Last cleanup</th>
                  </tr>
                </thead>
                <tbody>
                  {dash.accounts.map((a) => (
                    <tr key={a.account_id}>
                      <td>
                        <strong>{a.name}</strong>
                        <div className="muted small">{a.account_id}</div>
                      </td>
                      <td className="num">{money(a.cost_avoided_monthly)}</td>
                      <td className="num">{a.cleanups}</td>
                      <td className="num">{a.open_prs}</td>
                      <td>{a.last_cleanup ? timeAgo(a.last_cleanup) : 'Never'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card">
              <h2>Cleanups by status</h2>
              <StatusBars counts={dash.counts_by_status} />
            </div>
          </div>

          <div className="card">
            <h2>Recent cleanups</h2>
            {cleanups.length === 0 ? (
              <div className="empty">Nothing here yet.</div>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Account</th>
                    <th>Resources</th>
                    <th className="num">Per month</th>
                    <th>Status</th>
                    <th>Pull request</th>
                  </tr>
                </thead>
                <tbody>
                  {cleanups.map((c) => (
                    <tr key={`${c.account_id}-${c.run_id}`}>
                      <td>{shortDate(c.timestamp)}</td>
                      <td>{c.account_id}</td>
                      <td className="small">{c.resources.map((r) => r.resource_id).filter(Boolean).join(', ')}</td>
                      <td className="num">{money(c.monthly_savings_usd)}</td>
                      <td>
                        <StatusChip status={c.status} />
                      </td>
                      <td>{c.pr_url ? <Linkified text={c.pr_url} /> : <span className="muted">None</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </section>
  )
}
