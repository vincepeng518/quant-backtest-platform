"use client"
import { useMemo } from "react"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts"

interface Trade { pnl: number; [k: string]: any }

export function ProfitDistribution({ trades }: { trades: Trade[] }) {
  const data = useMemo(() => {
    const vals = trades.map(t => t.pnl).sort((a, b) => a - b)
    if (!vals.length) return []
    const min = vals[0], max = vals[vals.length - 1]
    const n = 15, size = (max - min) / n || 1
    const bins = Array.from({ length: n }, (_, i) => ({
      range: `${(min + i * size).toFixed(0)}–${(min + (i + 1) * size).toFixed(0)}`,
      mid: min + (i + 0.5) * size,
      count: 0,
    }))
    vals.forEach(v => {
      const idx = Math.min(Math.floor((v - min) / size), n - 1)
      bins[idx].count++
    })
    return bins
  }, [trades])

  return (
    <div className="rounded-xl border bg-card p-4">
      <h3 className="text-sm font-medium mb-3">P&L Distribution</h3>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data}>
          <XAxis dataKey="range" tick={{ fontSize: 9, fill: "#94a3b8" }} angle={-35} textAnchor="end" height={50} />
          <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} />
          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }} />
          <Bar dataKey="count" radius={[3, 3, 0, 0]}>
            {data.map((d, i) => <Cell key={i} fill={d.mid >= 0 ? "#22c55e" : "#ef4444"} fillOpacity={0.65} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
