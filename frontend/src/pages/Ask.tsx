import { useRef, useState } from 'react'
import { api } from '../api'
import { Linkified, Spinner } from '../components/Bits'

interface Turn {
  question: string
  text?: string
  tool?: string | null
  error?: string
}

const EXAMPLES = [
  'What was the last cleanup and how much cost was avoided?',
  'How much cost have we avoided in total?',
  'Which cleanups are still open?',
  'Which resource types save the most?',
]

export function Ask() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef<HTMLDivElement>(null)

  const send = async (q: string) => {
    const question = q.trim()
    if (!question || busy) return
    setText('')
    setBusy(true)
    setTurns((t) => [...t, { question }])
    try {
      const a = await api.ask(question)
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, text: a.text, tool: a.tool } : x)))
    } catch (e) {
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, error: e instanceof Error ? e.message : String(e) } : x)))
    } finally {
      setBusy(false)
      setTimeout(() => end.current?.scrollIntoView?.({ behavior: 'smooth' }), 50)
    }
  }

  return (
    <section className="ask">
      <div className="page-head">
        <div>
          <h1>Ask CostWarden</h1>
          <p className="muted">Answers come from the cleanup history, so every number is a recorded figure.</p>
        </div>
      </div>

      <div className="chat card">
        {turns.length === 0 && (
          <div className="chat-empty">
            <p>Try one of these:</p>
            <div className="examples">
              {EXAMPLES.map((q) => (
                <button key={q} className="chip-btn" onClick={() => void send(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className="turn">
            <div className="bubble bubble-user">{t.question}</div>
            {t.error ? (
              <div className="bubble bubble-error" role="alert">{t.error}</div>
            ) : t.text ? (
              <div className="bubble bubble-bot">
                <Linkified text={t.text} />
                {t.tool && <div className="tool-badge">Source: {t.tool}</div>}
              </div>
            ) : (
              <Spinner label="Looking it up" />
            )}
          </div>
        ))}
        <div ref={end} />
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault()
          void send(text)
        }}
      >
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about past cleanups" aria-label="Question" maxLength={500} />
        <button className="btn btn-primary" type="submit" disabled={busy || !text.trim()}>
          Ask
        </button>
      </form>
    </section>
  )
}
