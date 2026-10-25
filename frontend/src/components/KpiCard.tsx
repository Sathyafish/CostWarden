import { useCountUp } from './useCountUp'

interface Props {
  label: string
  value: number
  format: (n: number) => string
  hint?: string
  accent?: 'teal' | 'amber' | 'blue'
  big?: boolean
}

export function KpiCard({ label, value, format, hint, accent = 'teal', big = false }: Props) {
  const shown = useCountUp(value)
  return (
    <div className={`card kpi kpi-${accent}${big ? ' kpi-big' : ''}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" data-testid={`kpi-${label}`}>{format(shown)}</div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </div>
  )
}
