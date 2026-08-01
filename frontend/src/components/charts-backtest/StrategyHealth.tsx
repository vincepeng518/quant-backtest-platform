"use client"
interface Metrics {
  win_rate: number; profit_factor: number; sharpe_ratio: number
  max_drawdown?: number; total_trades: number; expectancy: number
  [k: string]: any
}

function score(m: Metrics) {
  let s = 0
  s += Math.min(m.win_rate * 40, 40)
  s += Math.min((m.profit_factor / 2) * 30, 30)
  s += Math.min((m.sharpe_ratio / 2) * 20, 20)
  s -= Math.min(((m.max_drawdown ?? 0) / 30) * 10, 10)
  return Math.round(Math.max(0, Math.min(100, s)))
}

function grade(s: number) {
  if (s >= 80) return { label: "Excellent", color: "text-green-400", bar: "bg-green-500" }
  if (s >= 60) return { label: "Good", color: "text-blue-400", bar: "bg-blue-500" }
  if (s >= 40) return { label: "Fair", color: "text-yellow-400", bar: "bg-yellow-500" }
  return { label: "Needs Improvement", color: "text-red-400", bar: "bg-red-500" }
}

function tips(m: Metrics) {
  const r: string[] = []
  if (m.win_rate < 0.5) r.push("Win rate below 50% — review entry signals")
  if (m.profit_factor < 1.5) r.push("Profit factor below 1.5 — risk/reward needs work")
  if ((m.max_drawdown ?? 0) > 15) r.push("Max drawdown > 15% — reduce position size")
  if (m.expectancy <= 0) r.push("Negative expectancy — strategy has no edge")
  if (!r.length) r.push("Strategy looks healthy — monitor and maintain")
  return r
}

export function StrategyHealth({ m }: { m: Metrics }) {
  const s = score(m); const g = grade(s); const recs = tips(m)
  return (
    <div className="rounded-xl border bg-card p-4">
      <h3 className="text-sm font-medium mb-2">Strategy Health</h3>
      <div className="flex items-center gap-3 mb-3">
        <span className={"text-3xl font-bold " + g.color}>{s}</span>
        <span className={"text-sm font-medium " + g.color}>{g.label}</span>
      </div>
      <div className="w-full h-2 rounded-full bg-muted mb-3">
        <div className={"h-full rounded-full " + g.bar} style={{ width: s + "%" }} />
      </div>
      <ul className="text-xs space-y-1 text-muted-foreground">
        {recs.map((r, i) => <li key={i}>• {r}</li>)}
      </ul>
    </div>
  )
}
