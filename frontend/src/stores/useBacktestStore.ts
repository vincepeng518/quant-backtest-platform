import { create } from 'zustand';
import { BacktestResult, BacktestConfig } from '@/types/api';
import { useToastStore } from '@/stores/useToastStore';
import api from '@/lib/api';

interface BacktestStore {
  status: 'idle' | 'running' | 'completed' | 'error' | 'lookahead_warning';
  progress: number;
  results: BacktestResult | null;
  error: string | null;
  lookaheadWarning: any | null;
  runBacktest: (config: BacktestConfig) => Promise<void>;
  reset: () => void;
}

export const useBacktestStore = create<BacktestStore>((set) => ({
  status: 'idle',
  progress: 0,
  results: null,
  error: null,
  lookaheadWarning: null,
  runBacktest: async (config) => {
    set({ status: 'running', progress: 0, error: null });
    let interval: ReturnType<typeof setInterval> | null = null;
    try {
      // Post task initiation
      const { task_id } = await api.runBacktest(config);

      // Poll progression state
      interval = setInterval(async () => {
        try {
          const progressData = await api.getBacktestStatus(task_id);
          set({ progress: progressData.progress });

          if (progressData.status === 'completed') {
            if (interval) clearInterval(interval);
            const results = await api.getBacktestResults(task_id);
            set({ status: 'completed', results });
            useToastStore.getState().push({
              kind: 'success',
              title: '回測完成',
              message: `${config?.symbol ?? ''} · Sharpe ${(results as any)?.metrics?.sharpe_ratio?.toFixed(2) ?? '—'}`,
            });
          } else if (progressData.status === 'error') {
            if (interval) clearInterval(interval);
            set({ status: 'error', error: progressData.error });
            useToastStore.getState().push({ kind: 'danger', title: '回測失敗', message: progressData.error ?? 'unknown' });
          } else if (progressData.status === 'lookahead_warning') {
            if (interval) clearInterval(interval);
            const results = await api.getBacktestResults(task_id);
            set({ status: 'lookahead_warning', lookaheadWarning: (results as any)?.lookahead_warning ?? null });
            useToastStore.getState().push({ kind: 'danger', title: '⚠ 未來函數偵測', message: '策略疑似使用未來數據，結果不可信' });
          }
        } catch (err: any) {
          if (interval) clearInterval(interval);
          set({ status: 'error', error: err.message });
          useToastStore.getState().push({ kind: 'danger', title: '回測錯誤', message: err?.message ?? String(err) });
        }
      }, 1000);

    } catch (err: any) {
      set({ status: 'error', error: err.message });
      useToastStore.getState().push({ kind: 'danger', title: '回測錯誤', message: err?.message ?? String(err) });
    }
  },
  reset: () => set({ status: 'idle', progress: 0, results: null, error: null }),
}));
