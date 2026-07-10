import { BacktestConfig, BacktestResult } from '@/types/api';

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
};
export default api;
