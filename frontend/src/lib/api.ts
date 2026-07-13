import {
  BacktestConfig,
  BacktestResult,
  StrategyPayload,
  StrategyTemplate,
  UserStrategy,
  AnalysisResult,
  OptimizeResult,
} from '@/types/api';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || '/api';

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const errorDetails = await response.text();
    throw new ApiError(response.status, errorDetails || 'API request error');
  }

  return response.json();
}

export const api = {
  getSymbols: () => request<any[]>('/data/symbols'),
  getOHLCV: (symbol: string, timeframe: string) =>
    request<any[]>(`/data/ohlcv?symbol=${symbol}&timeframe=${timeframe}`),
  runBacktest: (config: BacktestConfig) =>
    request<{ task_id: string }>('/backtest/run', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  getBacktestStatus: (taskId: string) =>
    request<{ status: string; progress: number; error?: string }>(`/backtest/status/${taskId}`),
  getBacktestResults: (taskId: string) => request<BacktestResult>(`/backtest/results/${taskId}`),

  uploadStrategy: (payload: StrategyPayload) =>
    request<UserStrategy>('/strategy/upload', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listUserStrategies: () => request<UserStrategy[]>('/strategy/user'),
  getUserStrategy: (id: string) => request<UserStrategy>(`/strategy/user/${id}`),
  updateStrategy: (id: string, payload: StrategyPayload) =>
    request<UserStrategy>(`/strategy/user/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  deleteStrategy: (id: string) =>
    request<{ status: string }>(`/strategy/user/${id}`, {
      method: 'DELETE',
    }),
  getTemplates: () => request<StrategyTemplate[]>('/strategy/templates'),

  runWalkForward: (config: any) =>
    request<{ task_id: string }>('/analysis/walk-forward', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  runMonteCarlo: (config: any) =>
    request<{ task_id: string }>('/analysis/monte-carlo', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  getAnalysisResults: (taskId: string) =>
    request<AnalysisResult>(`/analysis/results/${taskId}`),
  runOptimize: (config: any) =>
    request<{ task_id: string }>('/optimize/run', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  getOptimizeResults: (taskId: string) =>
    request<OptimizeResult>(`/optimize/results/${taskId}`),
  applyBestParams: () =>
    request<{ applied: boolean }>('/optimize/best-params', {
      method: 'POST',
    }),
};
export default api;
