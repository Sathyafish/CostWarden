import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { compactMoney, money, shortDate } from '../format'
import type { Dashboard } from '../types'

const GRID = '#1f2c47'
const AXIS = '#8fa3c4'
const TIP = { background: '#0e1729', border: '1px solid #1f2c47', borderRadius: 8, color: '#e6edf7' }

export function TrendChart({ data }: { data: Dashboard['trend'] }) {
  if (data.length === 0) return <Empty text="No merged cleanups yet." />
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="trend" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#2dd4bf" stopOpacity={0.45} />
            <stop offset="1" stopColor="#2dd4bf" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDate} stroke={AXIS} tickLine={false} />
        <YAxis tickFormatter={compactMoney} stroke={AXIS} tickLine={false} axisLine={false} width={60} />
        <Tooltip contentStyle={TIP} formatter={(v) => [money(Number(v)), 'Run-rate avoided']} labelFormatter={(l) => shortDate(String(l))} />
        <Area type="monotone" dataKey="value" stroke="#2dd4bf" strokeWidth={2.5} fill="url(#trend)" />
      </AreaChart>
    </ResponsiveContainer>
  )
}

const TYPE_COLORS = ['#2dd4bf', '#38bdf8', '#a78bfa', '#fbbf24', '#f472b6', '#34d399']

export function TypeChart({ data }: { data: Dashboard['by_resource_type'] }) {
  if (data.length === 0) return <Empty text="No merged cleanups yet." />
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, data.length * 46)}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tickFormatter={compactMoney} stroke={AXIS} tickLine={false} />
        <YAxis type="category" dataKey="resource_type" stroke={AXIS} tickLine={false} width={120} />
        <Tooltip contentStyle={TIP} cursor={{ fill: 'rgba(255,255,255,0.04)' }} formatter={(v) => [money(Number(v)), 'Avoided per month']} />
        <Bar dataKey="savings" radius={[0, 6, 6, 0]}>
          {data.map((_, i) => (
            <Cell key={i} fill={TYPE_COLORS[i % TYPE_COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

const STATUS_COLORS: Record<string, string> = { merged: '#34d399', proposed: '#fbbf24', rejected: '#8fa3c4', failed: '#f87171' }

export function StatusBars({ counts }: { counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  if (total === 0) return <Empty text="No cleanups yet." />
  return (
    <div className="status-bars">
      {Object.entries(counts).map(([status, n]) => (
        <div key={status} className="status-row">
          <span className="status-name">{status}</span>
          <div className="status-track">
            <div className="status-fill" style={{ width: `${(n / total) * 100}%`, background: STATUS_COLORS[status] ?? '#8fa3c4' }} />
          </div>
          <span className="status-count">{n}</span>
        </div>
      ))}
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>
}
