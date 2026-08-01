"use client"
interface Metrics {
  total_trades: number; winning_trades: number; losing_trades: number; win_rate: number
  total_return_pct: number; max_drawdown?: number; sharpe_ratio: number
  sortino_ratio: number; profit_factor: number; net_profit?: number
  calmar_ratio?: number; expectancy?: number; annual_return_pct?: number
  long_win_rate?: number; short_win_rate?: number
  long_pnl?: number; short_pnl?: number
  [k: string]: any
}

function Card({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-xl border bg-card p-3 flex flex-col">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className={"text-lg font-semibold " + (color || "")}>{value}</span>
    </div>
  )
}

export function StatsHighlights({ m }: { m: Metrics }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <Card label="Total Trades" value={String(m.total_trades)} />
      <Card label="Win Rate" value={(m.win_rate * 100).toFixed(1) + "%"} color={m.win_rate >= 0.5 ? "text-green-400" : "text-red-400"} />
      <Card label="Net P&L" value={"$" + (m.net_profit ?? 0).toFixed(2)} color={(m.net_profit ?? 0) >= 0 ? "text-green-400" : "text-red-400"} />
      <Card label="Total Return" value={m.total_return_pct.toFixed(1) + "%"} color={m.total_return_pct >= 0 ? "text-green-400" : "text-red-400"} />
      <Card label="Max Drawdown" value={"$" + (m.max_drawdown ?? 0).toFixed(2)} color="text-red-400" />
      <Card label="Sharpe Ratio" value={m.sharpe_ratio.toFixed(2)} color={m.sharpe_ratio >= 1 ? "text-green-400" : "text-yellow-400"} />
      <Card label="Profit Factor" value={m.profit_factor.toFixed(2)} color={m.profit_factor >= 1.5 ? "text-green-400" : "text-yellow-400"} />
      <Card label="Sortino Ratio" value={m.sortino_ratio.toFixed(2)} />
    </div>
  )
}
