import { useEffect, useState } from 'react'
import { api } from '../api'
import { DiffView, ErrorBanner, Linkified, Spinner, StatusChip } from '../components/Bits'
import { money } from '../format'
import type { Account, Pending, RunStatus } from '../types'

type ApprovePending = Extract<Pending, { type: 'approve_diff' }>

export function Runs({ onChanged }: { onChanged: () => void }) {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [accountId, setAccountId] = useState('')
  const [status, setStatus] = useState<RunStatus | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.accounts().then(setAccounts).catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  const run = async (label: string, fn: () => Promise<RunStatus>) => {
    setBusy(label)
    setError(null)
    try {
      const s = await fn()
      setStatus(s)
      if (s.done) onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const start = () => run('Discovering waste and drafting changes', () => api.startRun(accountId ? [accountId] : undefined))
  const resume = (label: string, value: Record<string, unknown>) => run(label, () => api.resume(status!.run_id, value))

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Runs and approvals</h1>
          <p className="muted">Nothing is pushed or applied until you approve. Reads are automatic; writes need a human.</p>
        </div>
        <div className="controls">
          <select value={accountId} onChange={(e) => setAccountId(e.target.value)} aria-label="Account to scan" disabled={!!busy}>
            <option value="">All accounts</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({a.id})
              </option>
            ))}
          </select>
          <button className="btn btn-primary" onClick={() => void start()} disabled={!!busy}>
            Start cleanup run
          </button>
        </div>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}
      {busy && <Spinner label={busy} />}

      {status && (
        <div className="stack">
          <div className="card">
            <div className="run-head">
              <span className="muted">Run</span> <code>{status.run_id}</code>
            </div>
            <div className="outcomes">
              {Object.keys(status.findings).length === 0 && Object.keys(status.outcomes).length === 0 && <span className="muted">No accounts scanned.</span>}
              {Array.from(new Set([...Object.keys(status.findings), ...Object.keys(status.outcomes)])).map((id) => (
                <div key={id} className="outcome">
                  <strong>{id}</strong>
                  <span className="muted small">{status.findings[id] ?? 0} findings</span>
                  {status.outcomes[id] && <StatusChip status={status.outcomes[id]} />}
                </div>
              ))}
            </div>
            {Object.entries(status.errors).map(([id, e]) => (
              <div key={id} className="banner banner-warn">{id}: {e}</div>
            ))}
          </div>

          {status.pending?.type === 'approve_diff' && <ApproveCard p={status.pending} busy={!!busy} onResume={resume} />}

          {status.pending?.type === 'confirm_merge' && (
            <div className="card">
              <h2>Confirm the merge for {status.pending.account_id}</h2>
              <p>
                Draft pull request: <Linkified text={status.pending.pr_url} />
              </p>
              <p className="muted">Review and merge it in GitHub, then confirm here so the plan step can run.</p>
              <div className="actions">
                <button className="btn btn-primary" disabled={!!busy} onClick={() => void resume('Running the plan', { merged: true })}>
                  The PR is merged, run the plan
                </button>
                <button className="btn btn-ghost" disabled={!!busy} onClick={() => void resume('Saving', { merged: false })}>
                  Not merged yet
                </button>
              </div>
            </div>
          )}

          {status.pending?.type === 'handle_error' && (
            <div className="card">
              <h2>A step failed for {status.pending.account_id}</h2>
              <div className="banner banner-error">{status.pending.step}: {status.pending.error}</div>
              <div className="actions">
                <button className="btn btn-primary" disabled={!!busy} onClick={() => void resume('Retrying', { action: 'retry' })}>
                  Retry
                </button>
                <button className="btn btn-ghost" disabled={!!busy} onClick={() => void resume('Skipping', { action: 'skip' })}>
                  Skip this account
                </button>
              </div>
            </div>
          )}

          {status.done && (
            <div className="banner banner-success">
              Run complete.
              {Object.entries(status.plans).map(([id, p]) => (
                <div key={id} className="small">Plan for {id}: {p.summary}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function ApproveCard({ p, busy, onResume }: { p: ApprovePending; busy: boolean; onResume: (label: string, v: Record<string, unknown>) => void }) {
  const [exclude, setExclude] = useState<Set<string>>(new Set())
  const kept = p.edited.filter((e) => !exclude.has(e.resource_id))
  const savings = kept.reduce((a, e) => a + e.monthly_savings_usd, 0)

  const toggle = (id: string) =>
    setExclude((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })

  return (
    <div className="card">
      <h2>
        Approve changes for {p.account_name} <span className="muted small">({p.account_id})</span>
      </h2>
      <div className="approve-top">
        <div className="kpi-inline">
          <div className="kpi-label">Estimated savings per month</div>
          <div className="kpi-value">{money(savings)}</div>
          {exclude.size > 0 && <div className="muted small">Excluding {exclude.size} resource(s)</div>}
        </div>
        <div className="risk">
          <div className="kpi-label">Risk summary</div>
          <p>{p.summary || 'No risk summary was generated.'}</p>
        </div>
      </div>

      <table className="table">
        <thead>
          <tr>
            <th>Include</th>
            <th>Resource</th>
            <th>Change</th>
            <th className="num">Per month</th>
            <th>Risk</th>
          </tr>
        </thead>
        <tbody>
          {p.edited.map((e) => (
            <tr key={e.resource_id} className={exclude.has(e.resource_id) ? 'row-off' : ''}>
              <td>
                <input type="checkbox" checked={!exclude.has(e.resource_id)} onChange={() => toggle(e.resource_id)} aria-label={`Include ${e.resource_id}`} />
              </td>
              <td>
                <code>{e.resource_id}</code>
                <div className="muted small">{e.address}</div>
              </td>
              <td>{e.action === 'resize' ? `${e.current ?? '?'} → ${e.recommended}` : 'Release (count = 0)'}</td>
              <td className="num">{money(e.monthly_savings_usd)}</td>
              <td>
                <span className={`chip chip-risk-${e.severity}`}>{e.severity}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {p.unmapped.length > 0 && (
        <div className="banner banner-warn">Not changed (no matching Terraform): {p.unmapped.map((u) => u.finding.resource_id).join(', ')}</div>
      )}

      <h3>Terraform diff</h3>
      <DiffView diff={p.diff} />
      <p className="muted small">{p.validation}</p>

      <div className="actions">
        <button className="btn btn-primary" disabled={busy || kept.length === 0} onClick={() => onResume('Opening the draft pull request', { approved: true, exclude: [...exclude] })}>
          Approve and open draft PR
        </button>
        <button className="btn btn-ghost" disabled={busy} onClick={() => onResume('Recording the rejection', { approved: false })}>
          Reject
        </button>
      </div>
    </div>
  )
}
