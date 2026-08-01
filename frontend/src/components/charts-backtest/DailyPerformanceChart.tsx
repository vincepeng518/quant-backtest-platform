"use client"
import { useMemo } from "react"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, Line, ComposedChart, Legend } from "recharts"

interface Trade { pnl: number; entry_time: any; [k: string]: any }

const fmt = (v: any, n: any) => [n === "pnl" ? "$" + v : v + "%", n === "pnl" ? "P&L" : "Win Rate"]

export function DailyPerformanceChart({ trades }: { trades: Trade[] }) {
  const data = useMemo(() => {
    const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    const acc: Record<string, { pnl: number; wins: number; total: number }> = {}
    days.forEach(d => (acc[d] = { pnl: 0, wins: 0, total: 0 }))
    trades.forEach(t => {
      const d = new Date(t.entry_time).getDay()
      const key = days[(d + 6) % 7]
      acc[key].pnl += t.pnl
      acc[key].total++
      if (t.pnl > 0) acc[key].wins++
    })
    return days.map(d => ({
      day: d,
      pnl: +acc[d].pnl.toFixed(2),
      winrate: acc[d].total ? +(acc[d].wins / acc[d].total * 100).toFixed(1) : 0,
      trades: acc[d].total,
    }))
  }, [trades])

  return (
    <div className="rounded-xl border bg-card p-4">
      <h3 className="text-sm font-medium mb-3">Daily Performance</h3>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={data}>
          <XAxis dataKey="day" tick={{ fontSize: 12, fill: "#94a3b8" }} />
          <YAxis yAxisId="pnl" tick={{ fontSize: 11, fill: "#94a3b8" }} />
          <YAxis yAxisId="wr" orientation="right" domain={[0, 100]} tick={{ fontSize: 11, fill: "#94a3b8" }} />
          <Tooltip
            contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
            formatter={fmt as any}
          />
          <Legend />
          <Bar yAxisId="pnl" dataKey="pnl" radius={[4, 4, 0, 0]} name="P&L">
            {data.map((d, i) => <Cell key={i} fill={d.pnl >= 0 ? "#22c55e" : "#ef4444"} fillOpacity={0.7} />)}
          </Bar>
          <Line yAxisId="wr" dataKey="winrate" stroke="#3b82f6" dot={{ r: 4 }} name="Win Rate %" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
