'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { PageShell } from '@/components/layout/PageShell';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
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

export default function HistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getBacktestHistory()
      .then(setItems)
      .catch((e) => setError(e?.message ?? 'failed to load history'))
      .finally(() => setLoading(false));
  }, []);

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
          <div className="divide-y divide-border/10">
            {items.map((it) => (
              <button
                key={it.task_id}
                onClick={() => router.push(`/backtest?task=${it.task_id}`)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface/50 text-left transition-colors"
              >
                <div>
                  <p className="text-sm font-mono text-text">{it.strategy ?? '—'} · {it.symbol ?? '—'} · {it.timeframe ?? '—'}</p>
                  <p className="text-xs text-textSecondary font-mono">{it.task_id} · {it.created_at?.slice(0, 19)?.replace('T', ' ')}</p>
                </div>
                <div className="text-right">
                  <p className={`text-sm font-mono ${it.sharpe != null && it.sharpe >= 0 ? 'text-success' : 'text-danger'}`}>
                    {it.sharpe != null ? it.sharpe.toFixed(3) : '—'}
                  </p>
                  <p className="text-xs text-textSecondary font-mono">{it.total_trades ?? 0} trades</p>
                </div>
              </button>
            ))}
          </div>
        )}
      </Card>
    </PageShell>
  );
}
