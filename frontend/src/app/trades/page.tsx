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
      const t = (r.ts ?? 0) / 1000; // ms->s
      const diff = now / 1000 - t;
      if (range === 'day') return diff <= 86400;
      if (range === 'month') return diff <= 86400 * 30;
      return true;
    });
  }, [records, range, now]);

  const stats = useMemo(() => {
    let totalPnl = 0, totalPos = 0, wins = 0, losses = 0;
    for (const r of filtered) {
      const p = pnlOf(r);
      totalPnl += p;
      totalPos += Number(r.positionValue ?? 0);
      if (p > 0) wins++;
      else if (p < 0) losses++;
    }
    const ratio = losses > 0 ? wins / losses : wins;
    return { totalPnl, totalPos, wins, losses, ratio };
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
      {/* 統計條 */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setRange(t.key)}
            className={`px-3 py-1.5 rounded-md text-sm font-mono transition-colors ${
              range === t.key
                ? 'bg-accent text-background font-medium'
                : 'bg-surface text-textSecondary hover:text-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Card className="p-4">
          <p className="text-xs text-textSecondary font-mono mb-1">P/L ({range === 'all' ? '全部' : range === 'month' ? '近30日' : '近24h'})</p>
          <p className={`text-xl font-mono font-semibold ${stats.totalPnl >= 0 ? 'text-accent' : 'text-danger'}`}>
            {stats.totalPnl >= 0 ? '+' : ''}{fmt(stats.totalPnl)}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-textSecondary font-mono mb-1">總倉位大小</p>
          <p className="text-xl font-mono font-semibold text-text">{fmt(stats.totalPos)}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-textSecondary font-mono mb-1">盈虧比 (W/L)</p>
          <p className="text-xl font-mono font-semibold text-text">{fmt(stats.ratio, 2)}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-textSecondary font-mono mb-1">筆數 (勝/負)</p>
          <p className="text-xl font-mono font-semibold text-text">{filtered.length} ({stats.wins}/{stats.losses})</p>
        </Card>
      </div>

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
    </PageShell>
  );
}
