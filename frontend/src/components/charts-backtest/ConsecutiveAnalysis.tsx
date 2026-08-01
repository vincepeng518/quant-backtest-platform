"use client"
import { useMemo } from "react"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts"

interface Trade { pnl: number; [k: string]: any }

export function ConsecutiveAnalysis({ trades }: { trades: Trade[] }) {
  const { streaks, condProbs } = useMemo(() => {
    const sorted = [...trades].sort((a, b) => new Date(a.entry_time).getTime() - new Date(b.entry_time).getTime())
    // streaks
    const s: { len: number; type: string; count: number }[] = []
    let cur = 1, curType = sorted[0]?.pnl >= 0 ? "W" : "L"
    for (let i = 1; i < sorted.length; i++) {
      const w = sorted[i].pnl >= 0 ? "W" : "L"
      if (w === curType) { cur++ } else { s.push({ len: cur, type: curType, count: 1 }); cur = 1; curType = w }
    }
    s.push({ len: cur, type: curType, count: 1 })
    // cond probs
    const seq = sorted.map(t => t.pnl >= 0 ? "W" : "L")
    let wAfterW = 0, wAfterL = 0, tW = 0, tL = 0
    for (let i = 1; i < seq.length; i++) {
      if (seq[i - 1] === "W") { tW++; if (seq[i] === "W") wAfterW++ }
      else { tL++; if (seq[i] === "W") wAfterL++ }
    }
    return {
      streaks: s,
      condProbs: { wAfterW: tW ? +(wAfterW / tW * 100).toFixed(1) : 0, wAfterL: tL ? +(wAfterL / tL * 100).toFixed(1) : 0, maxWin: Math.max(...s.filter(x => x.type === "W").map(x => x.len), 0), maxLoss: Math.max(...s.filter(x => x.type === "L").map(x => x.len), 0) },
    }
  }, [trades])

  const chartData = useMemo(() => {
    const m: Record<string, number> = {}
    streaks.forEach(s => { const k = `${s.type}${s.len}`; m[k] = (m[k] || 0) + 1 })
    return Object.entries(m).sort((a, b) => a[0].localeCompare(b[0])).map(([k, v]) => ({ streak: k, count: v }))
  }, [streaks])

  return (
    <div className="rounded-xl border bg-card p-4">
      <h3 className="text-sm font-medium mb-2">Consecutive Results</h3>
      <div className="flex gap-4 mb-3 text-xs">
        <span>P(W|W) = <b className="text-green-400">{condProbs.wAfterW}%</b></span>
        <span>P(W|L) = <b className="text-blue-400">{condProbs.wAfterL}%</b></span>
        <span>Max W streak: <b className="text-green-400">{condProbs.maxWin}</b></span>
        <span>Max L streak: <b className="text-red-400">{condProbs.maxLoss}</b></span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={chartData}>
          <XAxis dataKey="streak" tick={{ fontSize: 10, fill: "#94a3b8" }} />
          <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} />
          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }} />
          <Bar dataKey="count" radius={[3, 3, 0, 0]}>
            {chartData.map((d, i) => <Cell key={i} fill={d.streak.startsWith("W") ? "#22c55e" : "#ef4444"} fillOpacity={0.65} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
