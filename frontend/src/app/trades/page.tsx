'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { PageShell } from '@/components/layout/PageShell';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { api } from '@/lib/api';

interface TradeRec {
  symbol?: string;
  side?: string;
  positionAmt?: number;
  avgPrice?: number;
  exitPrice?: number;
  leverage?: number;
  unrealizedProfit?: number;
  realizedProfit?: number;
  pnlRatio?: number;
  positionValue?: number;
  liquidationPrice?: number;
  status?: string;
  ts?: number;
  _snapshot?: string;
}

type Range = 'all' | 'month' | 'day';

function pnlOf(r: TradeRec): number {
  return Number(r.realizedProfit ?? 0) + Number(r.unrealizedProfit ?? 0);
}

function fmt(n: number, d = 2): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}

// journalit 風格: 盈虧 -> 綠/紅階層 class
function heatClass(pnl: number): string {
  if (pnl === 0) return 'heat-empty';
  const a = Math.abs(pnl);
  let lvl = 1;
  if (a > 50) lvl = 4;
  else if (a > 20) lvl = 3;
  else if (a > 5) lvl = 2;
  return pnl > 0 ? `heat-profit-${lvl}` : `heat-loss-${lvl}`;
}

export default function TradesPage() {
  const [records, setRecords] = useState<TradeRec[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<Range>('all');

  useEffect(() => {
    api.getTrades()
      .then((d: any) => setRecords(d.records ?? []))
      .catch((e) => setError(e?.message ?? 'failed to load trades'))
      .finally(() => setLoading(false));
  }, []);

  const now = Date.now();
  const filtered = useMemo(() => {
    if (range === 'all') return records;
    return records.filter((r) => {
      const t = (r.ts ?? 0) / 1000;
      const diff = now / 1000 - t;
      if (range === 'day') return diff <= 86400;
      if (range === 'month') return diff <= 86400 * 30;
      return true;
    });
  }, [records, range, now]);

  const stats = useMemo(() => {
    let totalPnl = 0, totalPos = 0, wins = 0, losses = 0, scr = 0;
    let longPnl = 0, shortPnl = 0;
    let streak = 0, maxWinStreak = 0, maxLossStreak = 0;
    // 按 ts 排序算連續
    const sorted = [...filtered].sort((a, b) => (a.ts ?? 0) - (b.ts ?? 0));
    for (const r of sorted) {
      const p = pnlOf(r);
      totalPnl += p;
      totalPos += Number(r.positionValue ?? 0);
      if (p > 0) { wins++; streak = streak > 0 ? streak + 1 : 1; maxWinStreak = Math.max(maxWinStreak, streak); }
      else if (p < 0) { losses++; streak = streak < 0 ? streak - 1 : -1; maxLossStreak = Math.max(maxLossStreak, -streak); }
      else scr++;
      const s = String(r.side ?? '').toUpperCase();
      if (s.includes('LONG')) longPnl += p;
      else if (s.includes('SHORT')) shortPnl += p;
    }
    const closed = wins + losses;
    const winRate = closed > 0 ? (wins / closed) * 100 : 0;
    const avgPnl = closed > 0 ? totalPnl / closed : 0;
    return { totalPnl, totalPos, wins, losses, scr, winRate, avgPnl, longPnl, shortPnl, maxWinStreak, maxLossStreak };
  }, [filtered]);

  // PnL Calendar Heatmap (journalit 風格)
  const heatmap = useMemo(() => {
    const dayMap = new Map<string, number>();
    for (const r of filtered) {
      const t = (r.ts ?? 0) / 1000;
      if (!t) continue;
      const d = new Date(t * 1000);
      const key = d.toISOString().slice(0, 10);
      dayMap.set(key, (dayMap.get(key) ?? 0) + pnlOf(r));
    }
    // 產生近 12 週格子 (從今天往前)
    const days = [];
    const today = new Date();
    for (let i = 83; i >= 0; i--) { // 12週*7
      const dt = new Date(today);
      dt.setDate(dt.getDate() - i);
      const key = dt.toISOString().slice(0, 10);
      days.push({ key, pnl: dayMap.get(key) ?? 0, dow: dt.getDay() });
    }
    return days;
  }, [filtered]);

  const tabs: { key: Range; label: string }[] = [
    { key: 'all', label: '全部' },
    { key: 'month', label: '月' },
    { key: 'day', label: '日' },
  ];

  return (
    <PageShell
      eyebrow="Trades / journal"
      title="交易記錄"
      subtitle="自動抓取 BingX 持倉與歷史已平倉，永久保存於 GitHub。僅含客觀數據。"
    >
      {/* 範圍切換 */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setRange(t.key)}
            className={`px-3 py-1.5 rounded-md text-sm font-mono transition-colors ${
              range === t.key ? 'bg-accent text-background font-medium' : 'bg-surface text-textSecondary hover:text-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 統計卡 (journalit 風格擴充) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Card className="p-4">
          <p className="text-xs text-textSecondary font-mono mb-1">P/L ({range === 'all' ? '全部' : range === 'month' ? '近30日' : '近24h'})</p>
          <p className={`text-xl font-mono font-semibold ${stats.totalPnl >= 0 ? 'text-accent' : 'text-danger'}`}>
            {stats.totalPnl >= 0 ? '+' : ''}{fmt(stats.totalPnl)}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-textSecondary font-mono mb-1">勝率 / 筆數</p>
          <p className="text-xl font-mono font-semibold text-text">{fmt(stats.winRate, 1)}%</p>
          <p className="text-xs text-textSecondary font-mono">{stats.wins}W / {stats.losses}L / {stats.scr}平</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-textSecondary font-mono mb-1">平均盈虧</p>
          <p className={`text-xl font-mono font-semibold ${stats.avgPnl >= 0 ? 'text-accent' : 'text-danger'}`}>
            {stats.avgPnl >= 0 ? '+' : ''}{fmt(stats.avgPnl)}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-textSecondary font-mono mb-1">總倉位大小</p>
          <p className="text-xl font-mono font-semibold text-text">{fmt(stats.totalPos)}</p>
        </Card>
      </div>

      {/* 多空 + 連續 (第二排) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Card className="p-4">
          <p className="text-xs text-textSecondary font-mono mb-1">多頭 P/L</p>
          <p className={`text-lg font-mono font-semibold ${stats.longPnl >= 0 ? 'text-accent' : 'text-danger'}`}>
            {stats.longPnl >= 0 ? '+' : ''}{fmt(stats.longPnl)}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-textSecondary font-mono mb-1">空頭 P/L</p>
          <p className={`text-lg font-mono font-semibold ${stats.shortPnl >= 0 ? 'text-accent' : 'text-danger'}`}>
            {stats.shortPnl >= 0 ? '+' : ''}{fmt(stats.shortPnl)}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-textSecondary font-mono mb-1">最大連續盈利</p>
          <p className="text-lg font-mono font-semibold text-accent">{stats.maxWinStreak} 筆</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-textSecondary font-mono mb-1">最大連續虧損</p>
          <p className="text-lg font-mono font-semibold text-danger">{stats.maxLossStreak} 筆</p>
        </Card>
      </div>

      {/* PnL Calendar Heatmap (journalit ContributionsHeatmap 風格) */}
      <Card className="p-4 mb-6">
        <p className="text-xs text-textSecondary font-mono mb-3">PnL 日曆 (近 12 週, 綠=盈/紅=虧)</p>
        <div className="flex flex-wrap gap-1">
          {heatmap.map((d) => (
            <div
              key={d.key}
              className={`heat-cell ${heatClass(d.pnl)}`}
              title={`${d.key}: ${d.pnl >= 0 ? '+' : ''}${fmt(d.pnl)}`}
            />
          ))}
        </div>
        <div className="flex items-center gap-2 mt-3 text-xs font-mono text-textSecondary">
          <span>少</span>
          <span className="heat-cell heat-empty" />
          <span className="heat-cell heat-loss-2" />
          <span className="heat-cell heat-loss-4" />
          <span className="heat-cell heat-profit-2" />
          <span className="heat-cell heat-profit-4" />
          <span>多</span>
        </div>
      </Card>

      {/* 交易表格 */}
      <Card className="min-h-[300px]">
        {loading ? (
          <div className="flex justify-center py-12"><Spinner size="lg" /></div>
        ) : error ? (
          <p className="text-sm font-mono text-danger p-6">{error}</p>
        ) : records.length === 0 ? (
          <EmptyState title="No trades yet" description="Run bot/trade_bot.py to capture BingX data." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-mono">
              <thead>
                <tr className="text-textSecondary text-xs border-b border-border/20">
                  <th className="text-left px-3 py-2">Symbol</th>
                  <th className="text-left px-3 py-2">Side</th>
                  <th className="text-right px-3 py-2">開倉價</th>
                  <th className="text-right px-3 py-2">平倉價</th>
                  <th className="text-right px-3 py-2">槓桿</th>
                  <th className="text-right px-3 py-2">總倉位</th>
                  <th className="text-right px-3 py-2">盈虧</th>
                  <th className="text-right px-3 py-2">盈虧比</th>
                  <th className="text-left px-3 py-2">狀態</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r, i) => {
                  const p = pnlOf(r);
                  return (
                    <tr key={i} className="border-b border-border/10 hover:bg-surface/40">
                      <td className="px-3 py-2 text-text">{r.symbol}</td>
                      <td className="px-3 py-2 text-textSecondary">{r.side}</td>
                      <td className="px-3 py-2 text-right text-text">{r.avgPrice ? fmt(r.avgPrice) : '—'}</td>
                      <td className="px-3 py-2 text-right text-text">{r.exitPrice ? fmt(r.exitPrice) : '—'}</td>
                      <td className="px-3 py-2 text-right text-textSecondary">{r.leverage ? `${r.leverage}x` : '—'}</td>
                      <td className="px-3 py-2 text-right text-text">{r.positionValue ? fmt(r.positionValue) : '—'}</td>
                      <td className={`px-3 py-2 text-right ${p >= 0 ? 'text-accent' : 'text-danger'}`}>
                        {p >= 0 ? '+' : ''}{fmt(p)}
                      </td>
                      <td className="px-3 py-2 text-right text-textSecondary">{r.pnlRatio ? fmt(r.pnlRatio, 2) : '—'}</td>
                      <td className="px-3 py-2 text-textSecondary">{r.status}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <style jsx>{`
        .heat-cell {
          width: 11px; height: 11px; border-radius: 2px;
          background: rgba(var(--border-rgb, 55, 53, 47), 0.12);
        }
        .heat-empty { background: rgba(120, 120, 120, 0.15); }
        .heat-profit-1 { background: rgba(16, 185, 129, 0.25); }
        .heat-profit-2 { background: rgba(16, 185, 129, 0.45); }
        .heat-profit-3 { background: rgba(16, 185, 129, 0.70); }
        .heat-profit-4 { background: rgba(5, 150, 105, 0.90); }
        .heat-loss-1 { background: rgba(239, 68, 68, 0.25); }
        .heat-loss-2 { background: rgba(239, 68, 68, 0.45); }
        .heat-loss-3 { background: rgba(239, 68, 68, 0.70); }
        .heat-loss-4 { background: rgba(220, 38, 38, 0.90); }
      `}</style>
    </PageShell>
  );
}
