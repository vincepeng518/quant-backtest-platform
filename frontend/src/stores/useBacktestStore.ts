import { create } from 'zustand';
import { BacktestResult, BacktestConfig } from '@/types/api';
import { useToastStore } from '@/stores/useToastStore';

interface BacktestStore {
  status: 'idle' | 'running' | 'completed' | 'error';
  progress: number;
  results: BacktestResult | null;
  error: string | null;
  runBacktest: (config: BacktestConfig) => Promise<void>;
  reset: () => void;
}

export const useBacktestStore = create<BacktestStore>((set) => ({
  status: 'idle',
  progress: 0,
  results: null,
  error: null,
  runBacktest: async (config) => {
    set({ status: 'running', progress: 0, error: null });
    try {
      // Post task initiation
      const response = await fetch('/api/backtest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });

      if (!response.ok) throw new Error('Failed to run backtest task');
      const { task_id } = await response.json();

      // Poll progression state
      const interval = setInterval(async () => {
        try {
          const res = await fetch(`/api/backtest/status/${task_id}`);
          if (!res.ok) throw new Error('Progress polling failed');
          const progressData = await res.json();

          set({ progress: progressData.progress });

          if (progressData.status === 'done') {
            clearInterval(interval);
            const resultsRes = await fetch(`/api/backtest/results/${task_id}`);
            const results = await resultsRes.json();
            set({ status: 'completed', results });
            useToastStore.getState().push({
              kind: 'success',
              title: '回測完成',
              message: `${config?.symbol ?? ''} · Sharpe ${(results as any)?.metrics?.sharpe_ratio?.toFixed(2) ?? '—'}`,
            });
          } else if (progressData.status === 'error') {
            clearInterval(interval);
            set({ status: 'error', error: progressData.error });
            useToastStore.getState().push({ kind: 'danger', title: '回測失敗', message: progressData.error ?? 'unknown' });
          }
        } catch (err: any) {
          clearInterval(interval);
          set({ status: 'error', error: err.message });
          useToastStore.getState().push({ kind: 'danger', title: '回測錯誤', message: err?.message ?? String(err) });
        }
      }, 500);

    } catch (err: any) {
      set({ status: 'error', error: err.message });
      useToastStore.getState().push({ kind: 'danger', title: '回測錯誤', message: err?.message ?? String(err) });
    }
  },
  reset: () => set({ status: 'idle', progress: 0, results: null, error: null }),
}));
