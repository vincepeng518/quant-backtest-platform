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
    const f = q ? items.filter((it) =>
      (it.strategy ?? '').toLowerCase().includes(q) ||
      (it.symbol ?? '').toLowerCase().includes(q) ||
      it.task_id.toLowerCase().includes(q)
    ) : items;
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
          <div className="flex flex-col items-center justify-center py-12 gap-3">
            <Spinner size="lg" />
            <p className="text-sm text-textSecondary font-mono">載入回測記錄…</p>
          </div>
        ) : error ? (
          <p className="text-sm font-mono text-danger p-6">{error}</p>
        ) : items.length === 0 ? (
          <EmptyState title="暫無回測記錄" description="執行回測後，記錄會自動保存在這裡。" />
        ) : (
          <>
            {/* Search + sort bar */}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between px-4 pb-4 border-b border-border/10">
              <Input
                label=""
                placeholder="搜尋策略 / 幣種 / ID…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="max-w-xs"
              />
              <span className="text-xs font-mono text-textSecondary">
                {filtered.length} / {items.length} 筆
              </span>
            </div>

            {filtered.length === 0 ? (
              <div className="p-6"><EmptyState title="無符合結果" description="嘗試其他搜尋關鍵字" /></div>
            ) : (
              <div className="space-y-px">
                {filtered.map((it) => (
                  <button
                    key={it.task_id}
                    onClick={() => router.push(`/backtest?task=${it.task_id}`)}
                    className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface/50 text-left transition-colors rounded-sm [&:nth-child(odd)]:bg-surface/30"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-mono text-text truncate">
                        {it.strategy ?? '—'} · {it.symbol ?? '—'} · {it.timeframe ?? '—'}
                      </p>
                      <p className="text-xs text-textSecondary font-mono truncate">
                        {it.task_id} · {it.created_at?.slice(0, 19)?.replace('T', ' ')}
                      </p>
                    </div>
                    <div className="text-right shrink-0 ml-4">
                      <p className={`text-sm font-mono ${it.sharpe != null && it.sharpe >= 0 ? 'text-success' : 'text-danger'}`}>
                        {it.sharpe != null ? `SR ${it.sharpe.toFixed(2)}` : '—'}
                      </p>
                      <p className="text-xs text-textSecondary font-mono">{it.total_trades ?? 0} 筆交易</p>
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
