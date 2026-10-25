import { useState } from 'react'
import { loadConfig, saveConfig } from '../api'
import type { Info } from '../types'
import { Logo } from './Logo'

export type Tab = 'overview' | 'ask' | 'runs'

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'ask', label: 'Ask' },
  { id: 'runs', label: 'Runs and approvals' },
]

interface Props {
  tab: Tab
  onTab: (t: Tab) => void
  info: Info | null
  onConfigChanged: () => void
}

export function Header({ tab, onTab, info, onConfigChanged }: Props) {
  const [open, setOpen] = useState(false)
  const [cfg, setCfg] = useState(loadConfig())

  return (
    <header className="header">
      <Logo />
      <nav className="tabs" aria-label="Sections">
        {TABS.map((t) => (
          <button key={t.id} className={`tab${tab === t.id ? ' tab-active' : ''}`} onClick={() => onTab(t.id)} aria-current={tab === t.id ? 'page' : undefined}>
            {t.label}
          </button>
        ))}
      </nav>
      <div className="header-right">
        {info && (
          <div className="pills" title="Where this app is running">
            <span className="pill">{info.runtime === 'lambda' ? 'AWS Lambda' : 'Local agents'}</span>
            <span className="pill">{info.store === 'dynamo' ? 'DynamoDB' : 'In-memory'}</span>
            <span className="pill">LLM: {info.llm}</span>
          </div>
        )}
        <button className="btn btn-ghost" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          Settings
        </button>
        {open && (
          <div className="popover" role="dialog" aria-label="Settings">
            <label>
              API URL <small>(blank uses the dev proxy)</small>
              <input value={cfg.baseUrl} onChange={(e) => setCfg({ ...cfg, baseUrl: e.target.value })} placeholder="https://xxxx.lambda-url.us-east-1.on.aws" />
            </label>
            <label>
              API key
              <input type="password" value={cfg.apiKey} onChange={(e) => setCfg({ ...cfg, apiKey: e.target.value })} placeholder="x-api-key" />
            </label>
            <button
              className="btn btn-primary"
              onClick={() => {
                saveConfig(cfg)
                setOpen(false)
                onConfigChanged()
              }}
            >
              Save
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
