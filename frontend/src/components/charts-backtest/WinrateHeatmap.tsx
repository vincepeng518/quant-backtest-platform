"use client"
import { useMemo } from "react"

interface Trade { pnl: number; entry_time: any; [k: string]: any }

const DAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
const HOURS = Array.from({ length: 24 }, (_, i) => i)

function bg(wr: number) {
  if (wr >= 60) return "bg-green-500/20 text-green-400"
  if (wr >= 50) return "bg-yellow-500/15 text-yellow-400"
  if (wr >= 40) return "bg-orange-500/15 text-orange-400"
  return "bg-red-500/15 text-red-400"
}

export function WinrateHeatmap({ trades }: { trades: Trade[] }) {
  const grid = useMemo(() => {
    const m: Record<string, { w: number; t: number }> = {}
    trades.forEach(t => {
      const d = new Date(t.entry_time)
      const dk = DAYS[(d.getUTCDay() + 6) % 7]
      const hk = d.getUTCHours()
      const k = `${dk}-${hk}`
      if (!m[k]) m[k] = { w: 0, t: 0 }
      m[k].t++
      if (t.pnl > 0) m[k].w++
    })
    return m
  }, [trades])

  return (
    <div className="rounded-xl border bg-card p-4 overflow-x-auto">
      <h3 className="text-sm font-medium mb-3">Win Rate Heatmap (Day × Hour UTC)</h3>
      <table className="text-xs w-full">
        <thead>
          <tr><th className="p-1" />{HOURS.filter(h => h % 3 === 0).map(h => <th key={h} className="p-1 text-muted-foreground font-normal">{h}</th>)}</tr>
        </thead>
        <tbody>
          {DAYS.map(d => (
            <tr key={d}>
              <td className="p-1 text-muted-foreground font-medium">{d}</td>
              {HOURS.filter(h => h % 3 === 0).map(h => {
                const s = grid[`${d}-${h}`]
                const wr = s ? +(s.w / s.t * 100).toFixed(0) : 0
                return (
                  <td key={h} className={`p-1 text-center rounded ${s ? bg(wr) : "text-muted-foreground/30"}`}>
                    {s ? `${wr}%` : "—"}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
