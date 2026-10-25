import type { ReactNode } from 'react'
import { splitLinks, statusLabel } from '../format'

export function StatusChip({ status }: { status: string }) {
  return <span className={`chip chip-${status}`}>{statusLabel(status)}</span>
}

export function Linkified({ text }: { text: string }) {
  return (
    <>
      {splitLinks(text).map((p, i) =>
        p.href ? (
          <a key={i} href={p.href} target="_blank" rel="noreferrer">
            {p.text}
          </a>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </>
  )
}

export function ErrorBanner({ children, onRetry }: { children: ReactNode; onRetry?: () => void }) {
  return (
    <div className="banner banner-error" role="alert">
      <span>{children}</span>
      {onRetry && (
        <button className="btn btn-ghost" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="spinner-row" role="status">
      <span className="spinner" /> {label}
    </div>
  )
}

export function DiffView({ diff }: { diff: string }) {
  if (!diff) return <div className="empty">No file changes.</div>
  return (
    <pre className="diff" aria-label="Terraform diff">
      {diff.split('\n').map((line, i) => {
        const cls = line.startsWith('+++') || line.startsWith('---') ? 'diff-file' : line.startsWith('+') ? 'diff-add' : line.startsWith('-') ? 'diff-del' : line.startsWith('@@') ? 'diff-hunk' : ''
        return (
          <div key={i} className={cls}>
            {line || ' '}
          </div>
        )
      })}
    </pre>
  )
}
