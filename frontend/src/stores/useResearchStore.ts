import { create } from 'zustand';
import { api } from '@/lib/api';

interface ResearchState {
  type: 'market' | 'signal';
  symbol: string;
  timeframe: string;
  strategyId: string;
  status: 'idle' | 'running' | 'done' | 'error';
  result: any;
  error: string | null;
  set: (p: Partial<ResearchState>) => void;
  run: () => Promise<void>;
}

export const useResearchStore = create<ResearchState>((set, get) => ({
  type: 'market', symbol: 'BTC/USDT', timeframe: '1h', strategyId: 'ma_cross',
  status: 'idle', result: null, error: null,
  set: (p) => set(p),
  run: async () => {
    set({ status: 'running', error: null, result: null });
    try {
      const body: any = { type: get().type, symbol: get().symbol, timeframe: get().timeframe,
        start_date: '2024-05-01', end_date: '2024-06-01' };
      if (get().type === 'signal') body.strategy_id = get().strategyId;
      const { task_id } = await api.runResearch(body);
      const poll = setInterval(async () => {
        const r = await api.getResearchResults(task_id);
        if (r.status === 'completed') { clearInterval(poll); set({ result: r, status: 'done' }); }
        else if (r.status === 'error') { clearInterval(poll); set({ error: (r as any).error ?? 'failed', status: 'error' }); }
      }, 1000);
    } catch (e: any) { set({ error: e?.message ?? 'request failed', status: 'error' }); }
  },
}));
