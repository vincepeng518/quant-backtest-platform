'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { PageShell } from '@/components/layout/PageShell';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { api } from '@/lib/api';

interface HistoryItem {
  task_id: string;
  status: string;
  created_at: string;
  strategy: string;
  symbol: string;
  timeframe: string;
  sharpe: number;
  total_trades: number;
}

type SortKey = 'created_at' | 'sharpe' | 'total_trades' | 'strategy';

export default function HistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('created_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  useEffect(() => {
    api.getBacktestHistory()
      .then(setItems)
      .catch((e) => setError(e?.message ?? 'failed to load history'))
      .finally(() => setLoading(false));
  }, []);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
  };

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    let f = items;
    // Quick Sharpe filter: sr>2, sr>1
    const srMatch = q.match(/^sr>(\d+(?:\.\d+)?)$/);
    if (srMatch) {
      const cutoff = parseFloat(srMatch[1]);
      f = items.filter((it) => (it.sharpe ?? 0) > cutoff);
    } else if (q) {
      f = items.filter((it) =>
        (it.strategy ?? '').toLowerCase().includes(q) ||
        (it.symbol ?? '').toLowerCase().includes(q) ||
        it.task_id.toLowerCase().includes(q)
      );
    }
    return [...f].sort((a, b) => {
      let av: string | number, bv: string | number;
      switch (sortKey) {
        case 'sharpe': av = a.sharpe ?? 0; bv = b.sharpe ?? 0; break;
        case 'total_trades': av = a.total_trades ?? 0; bv = b.total_trades ?? 0; break;
        case 'strategy': av = (a.strategy ?? '').toLowerCase(); bv = (b.strategy ?? '').toLowerCase(); break;
        default: av = a.created_at ?? ''; bv = b.created_at ?? '';
      }
      if (typeof av === 'string') return sortDir === 'asc' ? av.localeCompare(bv as string) : (bv as string).localeCompare(av);
      return sortDir === 'asc' ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });
  }, [items, search, sortKey, sortDir]);

  const sortIndicator = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '';

  return (
    <PageShell
      eyebrow="History / records"
      title="回測歷史"
      subtitle="已儲存的回測運行記錄，點擊可還原該次結果進行檢視與匯出。"
    >
      <Card className="min-h-[300px]">
        {loading ? (
          <div className="flex flex-col gap-3 px-4 py-8">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-3.5">
                <div className="flex-1 space-y-2">
                  <div className="skeleton h-4 w-48" />
                  <div className="skeleton h-3 w-64" />
                </div>
                <div className="text-right space-y-2">
                  <div className="skeleton h-4 w-20 ml-auto" />
                  <div className="skeleton h-3 w-16 ml-auto" />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <p className="text-sm font-mono text-danger p-6">{error}</p>
        ) : items.length === 0 ? (
          <EmptyState title="暫無回測記錄" description="執行回測後，記錄會自動保存在這裡。" />
        ) : (
          <>
            {/* Search + sort bar */}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between px-4 pb-4 border-b border-border/10">
              <div className="flex items-center gap-2 flex-wrap">
                <Input
                  label=""
                  placeholder="搜尋策略 / 幣種 / ID…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="max-w-[200px]"
                />
                {/* Quick Sharpe filters */}
                {[
                  { label: 'SR>2', fn: () => setSearch('sr>2') },
                  { label: 'SR>1', fn: () => setSearch('sr>1') },
                  { label: '60W+', fn: () => setSearch('60') },
                ].map((f) => (
                  <button
                    key={f.label}
                    onClick={f.fn}
                    className="px-2.5 py-1 text-[10px] font-mono rounded-md border border-white/[0.08] bg-surface2/40 text-textSecondary hover:text-accent hover:border-accent/30 transition-colors"
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <span className="text-xs font-mono text-textSecondary">
                {filtered.length} / {items.length} 筆
              </span>
            </div>

            {filtered.length === 0 ? (
              <div className="p-6"><EmptyState title="無符合結果" description="嘗試其他搜尋關鍵字" /></div>
            ) : (
              <div className="divide-y divide-border/10">
                {filtered.map((it) => (
                  <button
                    key={it.task_id}
                    onClick={() => router.push(`/backtest?task=${it.task_id}`)}
                    className="w-full flex items-center justify-between px-4 md:px-5 py-3.5 hover:bg-surface/60 text-left transition-all duration-150 group border-l-2 border-transparent hover:border-accent/40"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-text group-hover:text-accent transition-colors">
                          {it.strategy ?? '—'}
                        </span>
                        <span className="font-mono text-xs text-textSecondary">
                          {it.symbol ?? '—'} · {it.timeframe ?? '—'}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="font-mono text-[11px] text-textSecondary/60 truncate">
                          {it.task_id}
                        </span>
                        <span className="font-mono text-[11px] text-textSecondary/40">·</span>
                        <span className="font-mono text-[11px] text-textSecondary/60">
                          {it.created_at?.slice(0, 19)?.replace('T', ' ')}
                        </span>
                      </div>
                    </div>
                    <div className="text-right shrink-0 ml-4 flex items-center gap-4">
                      <div className="text-right">
                        <p className={`text-sm font-mono font-semibold tabular-nums ${it.sharpe != null && it.sharpe >= 0 ? 'text-success' : 'text-danger'}`}>
                          {it.sharpe != null ? `SR ${it.sharpe.toFixed(2)}` : 'SR —'}
                        </p>
                        <p className="text-[11px] text-textSecondary font-mono tabular-nums">{it.total_trades ?? 0} trades</p>
                      </div>
                      <svg className="h-4 w-4 text-textSecondary/30 group-hover:text-accent/60 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                      </svg>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </Card>
    </PageShell>
  );
}
