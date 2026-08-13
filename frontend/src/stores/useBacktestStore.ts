import { create } from 'zustand';
import { BacktestResult, BacktestConfig } from '@/types/api';
import { useToastStore } from '@/stores/useToastStore';
import api, { ApiError } from '@/lib/api';

interface BacktestStore {
  status: 'idle' | 'running' | 'completed' | 'error' | 'lookahead_warning' | 'cancelled';
  stage: string;
  progress: number;
  results: BacktestResult | null;
  error: string | null;
  lookaheadWarning: any | null;
  cancelTaskId: string | null;
  _intervalRef: ReturnType<typeof setInterval> | null;
  cancelBacktest: () => Promise<void>;
  runBacktest: (config: BacktestConfig) => Promise<void>;
  reset: () => void;
}

export const useBacktestStore = create<BacktestStore>((set, get) => ({
  status: 'idle',
  stage: 'idle',
  progress: 0,
  results: null,
  error: null,
  lookaheadWarning: null,
  runBacktest: async (config) => {
    set({ status: 'running', progress: 0, error: null, stage: 'loading', results: null });
    const stopPoll = () => {
      const iv = get()._intervalRef;
      if (iv) { clearInterval(iv); set({ _intervalRef: null }); }
    };
    try {
      // Post task initiation
      const { task_id } = await api.runBacktest(config);
      set({ cancelTaskId: task_id });

      // Poll progression state
      const interval = setInterval(async () => {
        try {
          const progressData = await api.getBacktestStatus(task_id);
          set({ progress: progressData.progress, stage: progressData.stage ?? progressData.status });
          if (progressData.status === 'completed') {
            stopPoll();
            const results = await api.getBacktestResults(task_id);
            set({ status: 'completed', stage: 'completed', results });
            useToastStore.getState().push({
              kind: 'success',
              title: '回測完成',
              message: `${config?.symbol ?? ''} · Sharpe ${(results as any)?.metrics?.sharpe_ratio?.toFixed(2) ?? '—'}`,
            });
          } else if (progressData.status === 'cancelled') {
            stopPoll();
            set({ status: 'cancelled', stage: 'cancelled', results: null });
            useToastStore.getState().push({ kind: 'danger', title: '已中斷', message: '回測已由使用者取消' });
          } else if (progressData.status === 'error') {
            stopPoll();
            set({ status: 'error', error: progressData.error });
            useToastStore.getState().push({ kind: 'danger', title: '回測失敗', message: progressData.error ?? 'unknown' });
          } else if (progressData.status === 'lookahead_warning') {
            stopPoll();
            const results = await api.getBacktestResults(task_id);
            set({ status: 'lookahead_warning', lookaheadWarning: (results as any)?.lookahead_warning ?? null });
            useToastStore.getState().push({ kind: 'danger', title: '⚠ 未來函數偵測', message: '策略疑似使用未來數據，結果不可信' });
          }
        } catch (err: any) {
          stopPoll();
          set({ status: 'error', error: err.message });
          useToastStore.getState().push({ kind: 'danger', title: '回測錯誤', message: err?.message ?? String(err) });
        }
      }, 800);
      set({ _intervalRef: interval });

    } catch (err: any) {
      const msg = err instanceof ApiError && err.status === 422
        ? '請求格式錯誤 — 請檢查策略參數或數據源設定'
        : err.message;
      set({ status: 'error', error: msg });
      useToastStore.getState().push({ kind: 'danger', title: '回測錯誤', message: msg });
    }
  },
  cancelBacktest: async () => {
    const tid = get().cancelTaskId;
    // 立即介面停止(0.1s 內),再標記後端 cancel
    const iv = get()._intervalRef;
    if (iv) { clearInterval(iv); set({ _intervalRef: null }); }
    set({ status: 'cancelled', stage: 'cancelled', progress: -1 });
    if (tid) {
      try { await api.cancelBacktest(tid); } catch { /* best-effort */ }
    }
  },
  // 內部持有 task_id / interval(供 cancel)
  cancelTaskId: null as string | null,
  _intervalRef: null as ReturnType<typeof setInterval> | null,
  reset: () => set({ status: 'idle', progress: 0, results: null, error: null, stage: 'idle', cancelTaskId: null, _intervalRef: null }),
}));
