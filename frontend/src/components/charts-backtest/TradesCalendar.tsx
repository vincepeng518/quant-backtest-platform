"use client"
import { useMemo, useState } from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"

interface Trade { pnl: number; entry_time: any; [k: string]: any }

function fmtDate(d: Date) { return d.toISOString().slice(0, 10) }

export function TradesCalendar({ trades }: { trades: Trade[] }) {
  const [offset, setOffset] = useState(0)
  const now = new Date()
  const month = new Date(now.getFullYear(), now.getMonth() + offset, 1)

  const byDay = useMemo(() => {
    const m: Record<string, { pnl: number; wins: number; total: number }> = {}
    trades.forEach(t => {
      const k = fmtDate(new Date(t.entry_time))
      if (!m[k]) m[k] = { pnl: 0, wins: 0, total: 0 }
      m[k].pnl += t.pnl; m[k].total++
      if (t.pnl > 0) m[k].wins++
    })
    return m
  }, [trades])

  const year = month.getFullYear(), mon = month.getMonth()
  const first = new Date(year, mon, 1).getDay()
  const days = new Date(year, mon + 1, 0).getDate()
  const cells: (number | null)[] = []
  for (let i = 0; i < (first + 6) % 7; i++) cells.push(null)
  for (let d = 1; d <= days; d++) cells.push(d)

  const color = (pnl: number) => pnl > 0 ? "text-green-400" : pnl < 0 ? "text-red-400" : "text-muted-foreground"
  const bg = (pnl: number) => pnl > 0 ? "bg-green-500/10" : pnl < 0 ? "bg-red-500/10" : ""

  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="flex items-center justify-between mb-3">
        <button onClick={() => setOffset(o => o - 1)} className="p-1 hover:bg-muted rounded"><ChevronLeft size={16} /></button>
        <h3 className="text-sm font-medium">{year}-{String(mon + 1).padStart(2, "0")}</h3>
        <button onClick={() => setOffset(o => o + 1)} className="p-1 hover:bg-muted rounded"><ChevronRight size={16} /></button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-xs">
        {["M","T","W","T","F","S","S"].map((d, i) => <div key={i} className="text-muted-foreground py-1">{d}</div>)}
        {cells.map((d, i) => {
          if (d === null) return <div key={i} />
          const k = fmtDate(new Date(year, mon, d))
          const s = byDay[k]
          return (
            <div key={i} className={`rounded py-1.5 ${s ? bg(s.pnl) : ""}`}>
              <div className="text-xs">{d}</div>
              {s && <div className={`text-[10px] font-mono ${color(s.pnl)}`}>{s.pnl >= 0 ? "+" : ""}{s.pnl.toFixed(1)}</div>}
            </div>
          )
        })}
      </div>
    </div>
  )
}
