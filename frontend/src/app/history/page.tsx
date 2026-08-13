'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { PageShell } from '@/components/layout/PageShell';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { useToastStore } from '@/stores/useToastStore';
import api from '@/lib/api';

interface HistoryItem {
  task_id: string;
  status: string;
  created_at: string;
  strategy: string;
  symbol: string;
  timeframe: string;
  sharpe: number;
  total_trades: number;
  config?: { strategy?: { template_id?: string; params?: Record<string, any> }; symbol?: string; timeframe?: string; start_date?: string; end_date?: string };
}

type SortKey = 'date' | 'sharpe' | 'trades';

export default function HistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('date');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [search, setSearch] = useState('');
  const [strategyFilter, setStrategyFilter] = useState('all');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);

  const toggleSel = (tid: string) =>
    setSelected((prev) => { const n = new Set(prev); n.has(tid) ? n.delete(tid) : n.add(tid); return n; });

  const deleteSelected = () => {
    const ids = Array.from(selected);
    if (!ids.length) return;
    setDeleting(true);
    api.deleteBacktestHistory(ids)
      .then((r) => {
        const del = new Set(r.deleted ?? []);
        setItems((prev) => prev.filter((i) => !del.has(i.task_id)));
        setSelected(new Set());
        useToastStore.getState().push({ kind: 'success', title: '已刪除', message: `刪除 ${r.deleted?.length ?? 0} 筆` });
        if (r.failed?.length) useToastStore.getState().push({ kind: 'danger', title: '部分刪除失敗', message: JSON.stringify(r.failed[0]).slice(0, 120) });
      })
      .catch((e) => useToastStore.getState().push({ kind: 'danger', title: '刪除失敗', message: e?.message ?? String(e) }))
      .finally(() => setDeleting(false));
  };

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

  const sortIcon = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '';

  const strategies = useMemo(() => {
    const s = new Set(items.map((i) => i.strategy).filter(Boolean));
    return ['all', ...Array.from(s).sort()];
  }, [items]);

  const filtered = useMemo(() => {
    let f = items;
    if (search) {
      const q = search.toLowerCase();
      f = f.filter((i) =>
        (i.strategy?.toLowerCase() ?? '').includes(q) ||
        (i.symbol?.toLowerCase() ?? '').includes(q) ||
        i.task_id.includes(q)
      );
    }
    if (strategyFilter !== 'all') f = f.filter((i) => i.strategy === strategyFilter);
    return f;
  }, [items, search, strategyFilter]);

  const sorted = useMemo(() => {
    const f = [...filtered];
    const dir = sortDir === 'asc' ? 1 : -1;
    f.sort((a, b) => {
      if (sortKey === 'date') return dir * (new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
      if (sortKey === 'sharpe') return dir * ((a.sharpe ?? -999) - (b.sharpe ?? -999));
      if (sortKey === 'trades') return dir * ((a.total_trades ?? 0) - (b.total_trades ?? 0));
      return 0;
    });
    return f;
  }, [filtered, sortKey, sortDir]);

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
          <div className="flex flex-col items-center justify-center gap-3 p-6 text-center">
            <p className="text-sm text-danger">載入回測歷史失敗。</p>
            <p className="text-xs font-mono text-textSecondary max-w-md break-all">{error}</p>
            <button
              onClick={() => {
                setLoading(true);
                setError(null);
                api.getBacktestHistory()
                  .then(setItems)
                  .catch((e) => setError(e?.message ?? 'failed to load history'))
                  .finally(() => setLoading(false));
              }}
              className="mt-1 rounded-md border border-accCyan/30 px-4 py-1.5 text-sm text-accCyan hover:bg-accCyan/10 transition-colors"
            >
              重試
            </button>
          </div>
        ) : items.length === 0 ? (
          <EmptyState title="暫無回測記錄" description="執行回測後，記錄會自動保存在這裡。" />
        ) : (
          <>
            {/* Filters */}
            <div className="flex flex-col gap-3 px-4 pb-3 sm:flex-row sm:items-center">
              <Input
                placeholder="搜尋策略 / 標的 / ID…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="sm:max-w-xs"
              />
              <select
                value={strategyFilter}
                onChange={(e) => setStrategyFilter(e.target.value)}
                className="rounded border border-border/20 bg-surface px-3 py-1.5 text-sm font-mono text-text outline-none focus:border-accent"
              >
                {strategies.map((s) => (
                  <option key={s} value={s}>{s === 'all' ? '全部策略' : s}</option>
                ))}
              </select>
              <span className="ml-auto text-xs text-textSecondary font-mono">{sorted.length} / {items.length} 筆</span>
              {selected.size > 0 && (
                <button
                  onClick={deleteSelected}
                  disabled={deleting}
                  className="shrink-0 rounded-md border border-danger/30 px-3 py-1.5 text-xs font-mono text-danger hover:bg-danger/10 transition-colors disabled:opacity-50"
                >
                  {deleting ? '刪除中…' : `批次刪除 (${selected.size})`}
                </button>
              )}
            </div>

            {/* Sortable header */}
            <div className="hidden border-b border-border/10 px-4 pb-2 text-xs font-semibold uppercase tracking-wider text-textSecondary sm:flex sm:justify-between">
              <button onClick={() => toggleSort('date')} className="hover:text-text">
                日期{sortIcon('date')}
              </button>
              <div className="flex gap-6">
                <button onClick={() => toggleSort('sharpe')} className="w-20 text-right hover:text-text">
                  Sharpe{sortIcon('sharpe')}
                </button>
                <button onClick={() => toggleSort('trades')} className="w-20 text-right hover:text-text">
                  Trades{sortIcon('trades')}
                </button>
              </div>
            </div>

            {/* List */}
            <div className="divide-y divide-border/10">
              {sorted.map((it) => (
                <div
                  key={it.task_id}
                  onClick={() => router.push(`/backtest?task=${it.task_id}`)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface/50 text-left transition-colors cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selected.has(it.task_id)}
                    onChange={() => toggleSel(it.task_id)}
                    onClick={(e) => e.stopPropagation()}
                    className="mr-3 h-4 w-4 accent-accent"
                    aria-label="選擇"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-mono text-text">
                      {it.strategy ?? '—'} · {it.symbol ?? '—'} · {it.timeframe ?? '—'}
                    </p>
                    <p className="truncate text-xs text-textSecondary font-mono">
                      {it.task_id} · {it.created_at?.slice(0, 19)?.replace('T', ' ')}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-4 text-right">
                    <p className={`w-20 text-sm font-mono ${it.sharpe != null && it.sharpe >= 0 ? 'text-success' : 'text-danger'}`}>
                      {it.sharpe != null ? it.sharpe.toFixed(3) : '—'}
                    </p>
                    <p className="w-20 text-xs text-textSecondary font-mono">{it.total_trades ?? 0}</p>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        const c = (it as any).config;
                        if (c) {
                          try {
                            localStorage.setItem('copyBacktestConfig', JSON.stringify({
                              strategy: c.strategy?.template_id ?? it.strategy,
                              symbol: c.symbol ?? it.symbol,
                              timeframe: c.timeframe ?? it.timeframe,
                              params: c.strategy?.params ?? {},
                              start_date: c.start_date ?? '',
                              end_date: c.end_date ?? '',
                            }));
                            router.push('/backtest?copy=1');
                          } catch { /* ignore */ }
                        }
                      }}
                      className="rounded border border-accent/30 px-2 py-1 text-xs font-mono text-accent hover:bg-accent/10 transition-colors"
                    >
                      複製參數
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </Card>
    </PageShell>
  );
}
