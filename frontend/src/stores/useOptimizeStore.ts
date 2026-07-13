import { create } from 'zustand';
import api from '@/lib/api';
import { useToastStore } from '@/stores/useToastStore';

export interface ParamRangeUI {
  id: string;
  name: string;
  min: number;
  max: number;
  step: number;
}

interface OptimizeStore {
  status: 'idle' | 'running' | 'completed' | 'error';
  progress: number;
  error: string | null;
  bestParams: Record<string, any> | null;
  bestScore: number | null;
  grid: any | null;
  trials: { params: Record<string, any>; score: number }[];
  strategyId: string;
  symbol: string;
  timeframe: string;
  source: string;
  paramSpace: ParamRangeUI[];
  // Engine realism (opt-in)
  enableFunding: boolean;
  fundingInterval: number;
  fundingRate: number;
  enablePerp: boolean;
  leverage: number;
  maintMargin: number;
  enableExchange: boolean;
  makerFee: number;
  takerFee: number;
  latencyBars: number;
  bookSlippage: number;
  setStrategy: (id: string) => void;
  setMarket: (m: { symbol: string; timeframe: string; source: string }) => void;
  addParam: (name: string) => void;
  updateParam: (id: string, patch: Partial<ParamRangeUI>) => void;
  removeParam: (id: string) => void;
  runOptimization: () => Promise<void>;
  reset: () => void;
}

const uid = () => Math.random().toString(36).slice(2, 9);

export const useOptimizeStore = create<OptimizeStore>((set, get) => ({
  status: 'idle',
  progress: 0,
  error: null,
  bestParams: null,
  bestScore: null,
  grid: null,
  trials: [],
  strategyId: 'ma_cross',
  symbol: 'BTC/USDT',
  timeframe: '1h',
  source: 'test',
  paramSpace: [
    { id: uid(), name: 'fast_period', min: 5, max: 20, step: 1 },
    { id: uid(), name: 'slow_period', min: 21, max: 60, step: 1 },
  ],
  enableFunding: false,
  fundingInterval: 8,
  fundingRate: 0.0001,
  enablePerp: false,
  leverage: 10,
  maintMargin: 0.005,
  enableExchange: false,
  makerFee: 0.0002,
  takerFee: 0.0005,
  latencyBars: 0,
  bookSlippage: 0.0005,
  setStrategy: (id) => set({ strategyId: id }),
  setMarket: (m) => set(m),
  addParam: (name) =>
    set((s) => ({ paramSpace: [...s.paramSpace, { id: uid(), name, min: 1, max: 10, step: 1 }] })),
  updateParam: (id, patch) =>
    set((s) => ({ paramSpace: s.paramSpace.map((p) => (p.id === id ? { ...p, ...patch } : p)) })),
  removeParam: (id) =>
    set((s) => ({ paramSpace: s.paramSpace.filter((p) => p.id !== id) })),
  runOptimization: async () => {
    const {
      strategyId, symbol, timeframe, source, paramSpace,
      enableFunding, fundingInterval, fundingRate,
      enablePerp, leverage, maintMargin,
      enableExchange, makerFee, takerFee, latencyBars, bookSlippage,
    } = get();
    set({ status: 'running', progress: 0, error: null, bestParams: null, bestScore: null, grid: null, trials: [] });
    try {
      const payload: Record<string, any> = {
        strategy_id: strategyId,
        symbol,
        timeframe,
        source,
        param_space: paramSpace.map((p) => ({ name: p.name, min: p.min, max: p.max, step: p.step })),
      };
      if (enableFunding) {
        payload.funding = { enabled: true, interval_hours: Number(fundingInterval), default_rate: Number(fundingRate) };
      }
      if (enablePerp) {
        payload.perpetual = { enabled: true, leverage: Number(leverage), maintenance_margin_rate: Number(maintMargin) };
      }
      if (enableExchange) {
        payload.exchange = {
          enabled: true,
          maker_fee: Number(makerFee),
          taker_fee: Number(takerFee),
          latency_bars: Number(latencyBars),
          book_base_slippage: Number(bookSlippage),
        };
      }
      const { task_id } = await api.runOptimize(payload);
      const poll = setInterval(async () => {
        try {
          const data = await api.getOptimizeResults(task_id);
          set({ progress: data.status === 'completed' ? 100 : 50 });
          if (data.status === 'completed') {
            clearInterval(poll);
            set({ status: 'completed', bestParams: data.best_params, bestScore: data.best_score, grid: data.grid, trials: data.trials });
            useToastStore.getState().push({ kind: 'success', title: '優化完成', message: data.best_score != null ? `最佳 Sharpe ${Number(data.best_score).toFixed(2)}` : undefined });
          } else if (data.status === 'error') {
            clearInterval(poll);
            set({ status: 'error', error: (data as any).error ?? 'optimization failed' });
            useToastStore.getState().push({ kind: 'danger', title: '優化失敗', message: (data as any).error ?? 'optimization failed' });
          }
        } catch (e) {
          clearInterval(poll);
          set({ status: 'error', error: 'polling failed' });
          useToastStore.getState().push({ kind: 'danger', title: '優化失敗', message: 'polling failed' });
        }
      }, 1500);
    } catch (e: any) {
      set({ status: 'error', error: e?.message ?? 'failed to start' });
      useToastStore.getState().push({ kind: 'danger', title: '優化失敗', message: e?.message ?? 'failed to start' });
    }
  },
  reset: () => set({ status: 'idle', progress: 0, error: null, bestParams: null, bestScore: null, grid: null, trials: [] }),
}));
