'use client';

import { useEffect, useState } from 'react';
import { api } from './api';

export interface HistoryRow {
  task_id: string;
  status: string;
  created_at: string;
  strategy: string | null;
  symbol: string | null;
  timeframe: string | null;
  sharpe: number | null;
  total_trades: number | null;
}

export interface DashboardStats {
  total: number;
  avgSharpe: number | null;
  bestRun: HistoryRow | null;
  worstRun: HistoryRow | null;
}

function computeStats(rows: HistoryRow[]): DashboardStats {
  const withSharpe = rows.filter((r) => typeof r.sharpe === 'number');
  if (withSharpe.length === 0) {
    return { total: rows.length, avgSharpe: null, bestRun: null, worstRun: null };
  }
  const sorted = [...withSharpe].sort((a, b) => (b.sharpe as number) - (a.sharpe as number));
  const avg = withSharpe.reduce((s, r) => s + (r.sharpe as number), 0) / withSharpe.length;
  return {
    total: rows.length,
    avgSharpe: Math.round(avg * 1000) / 1000,
    bestRun: sorted[0],
    worstRun: sorted[sorted.length - 1],
  };
}

export function useDashboard() {
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.getBacktestHistory()
      .then((data: HistoryRow[]) => {
        if (!alive) return;
        setRows(data);
        setLoading(false);
      })
      .catch((e) => {
        if (!alive) return;
        setError(String(e?.message ?? e));
        setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  return { rows, loading, error, stats: computeStats(rows) };
}
