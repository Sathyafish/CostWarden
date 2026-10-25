export function money(n: number, digits = 2): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function compactMoney(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  if (Math.abs(n) >= 10_000) return `$${(n / 1000).toFixed(1)}K`
  return money(n, 0)
}

export function shortDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

export function timeAgo(iso: string, now: Date = new Date()): string {
  const diff = now.getTime() - new Date(iso).getTime()
  const days = Math.floor(diff / 86_400_000)
  if (Number.isNaN(days)) return iso
  if (days <= 0) return 'today'
  if (days === 1) return '1 day ago'
  return `${days} days ago`
}

const URL_RE = /(https?:\/\/[^\s)]+)/g

/** Split text into plain and link parts so URLs can be rendered as anchors.
 *  Trailing punctuation stays in the text, not in the link. */
export function splitLinks(text: string): { text: string; href?: string }[] {
  const out: { text: string; href?: string }[] = []
  for (const part of text.split(URL_RE)) {
    if (part === '') continue
    if (!/^https?:\/\//.test(part)) {
      out.push({ text: part })
      continue
    }
    const url = part.replace(/[.,;]+$/, '')
    out.push({ text: url, href: url })
    if (url.length < part.length) out.push({ text: part.slice(url.length) })
  }
  // merge neighbouring plain-text parts (a link's trailing punctuation joins the text after it)
  return out.reduce<{ text: string; href?: string }[]>((acc, p) => {
    const last = acc[acc.length - 1]
    if (last && !last.href && !p.href) last.text += p.text
    else acc.push({ ...p })
    return acc
  }, [])
}

export function statusLabel(status: string): string {
  return status.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())
}
