"use client"
import { useMemo } from "react"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, Line, ComposedChart, Legend } from "recharts"

interface Trade { pnl: number; entry_time: any; [k: string]: any }

export function HourlyPerformanceChart({ trades }: { trades: Trade[] }) {
  const data = useMemo(() => {
    const acc: Record<number, { pnl: number; wins: number; total: number }> = {}
    for (let h = 0; h < 24; h++) acc[h] = { pnl: 0, wins: 0, total: 0 }
    trades.forEach(t => {
      const h = new Date(t.entry_time).getUTCHours()
      acc[h].pnl += t.pnl
      acc[h].total++
      if (t.pnl > 0) acc[h].wins++
    })
    return Array.from({ length: 24 }, (_, h) => ({
      hour: `${h}:00`,
      pnl: +acc[h].pnl.toFixed(2),
      winrate: acc[h].total ? +(acc[h].wins / acc[h].total * 100).toFixed(1) : 0,
      trades: acc[h].total,
    }))
  }, [trades])

  return (
    <div className="rounded-xl border bg-card p-4">
      <h3 className="text-sm font-medium mb-3">Hourly Performance (UTC)</h3>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={data}>
          <XAxis dataKey="hour" tick={{ fontSize: 11, fill: "#94a3b8" }} interval={2} />
          <YAxis yAxisId="pnl" tick={{ fontSize: 11, fill: "#94a3b8" }} />
          <YAxis yAxisId="wr" orientation="right" domain={[0, 100]} tick={{ fontSize: 11, fill: "#94a3b8" }} />
          <Tooltip
            contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
            formatter={(v: any, n: any) => [n === "pnl" ? `$${v}` : `${v}%`, n === "pnl" ? "P&L" : "Win Rate"]}
          />
          <Legend />
          <Bar yAxisId="pnl" dataKey="pnl" radius={[3, 3, 0, 0]} name="P&L">
            {data.map((d, i) => <Cell key={i} fill={d.pnl >= 0 ? "#14b8a6" : "#f43f5e"} fillOpacity={0.65} />)}
          </Bar>
          <Line yAxisId="wr" dataKey="winrate" stroke="#6366f1" dot={{ r: 3 }} name="Win Rate %" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
