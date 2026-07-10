import { create } from 'zustand';

interface ParameterRange {
  name: string;
  min: number;
  max: number;
  step: number;
}

interface OptimizeStore {
  status: 'idle' | 'running' | 'completed' | 'error';
  progress: number;
  bestParams: Record<string, any> | null;
  bestScore: number | null;
  runOptimization: (strategyId: string, space: ParameterRange[]) => Promise<void>;
  reset: () => void;
}

export const useOptimizeStore = create<OptimizeStore>((set) => ({
  status: 'idle',
  progress: 0,
  bestParams: null,
  bestScore: null,
  runOptimization: async (strategyId, space) => {
    set({ status: 'running', progress: 0 });
    try {
      const response = await fetch('/api/optimize/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy_id: strategyId, param_space: space }),
      });
      if (!response.ok) throw new Error('Optimization failed to start');
      const { task_id } = await response.json();

      const poll = setInterval(async () => {
        const res = await fetch(`/api/optimize/results/${task_id}`);
        if (res.ok) {
          const data = await res.json();
          set({ progress: data.progress });
          if (data.status === 'done') {
            clearInterval(poll);
            set({
              status: 'completed',
              bestParams: data.best_params,
              bestScore: data.best_score,
            });
          }
        }
      }, 1000);
    } catch {
      set({ status: 'error' });
    }
  },
  reset: () => set({ status: 'idle', progress: 0, bestParams: null, bestScore: null }),
}));
