import {
  BacktestConfig,
  BacktestResult,
  StrategyPayload,
  StrategyTemplate,
  UserStrategy,
  AnalysisResult,
  OptimizeResult,
  MonitorStats,
  ResearchResult,
  AdminOverview,
  MonitoredSymbol,
  CredentialStatus,
  TaskHistoryItem,
  UsageStat,
  SiteConfig,
  SiteConfigUpdate,
} from '@/types/api';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || '/api';
const ADMIN_TOKEN = process.env.NEXT_PUBLIC_ADMIN_TOKEN || '';

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> | undefined),
  };
  if (ADMIN_TOKEN) headers['Authorization'] = `Bearer ${ADMIN_TOKEN}`;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000); // 30s timeout (Railway cold start + GitHub fetch)

  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    });

    if (!response.ok) {
      const errorDetails = await response.text();
      throw new ApiError(response.status, errorDetails || 'API request error');
    }

    return response.json();
  } catch (e: any) {
    if (e.name === 'AbortError') {
      throw new ApiError(408, '請求超時 (10s) — 後端可能未響應');
    }
    throw e;
  } finally {
    clearTimeout(timeout);
  }
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
  getBacktestHistory: () => request<any[]>('/backtest/history'),
  getMonitorStats: () => request<MonitorStats>('/monitoring/stats'),
  getMonitorTrades: (limit = 50) =>
    request<{ trades: any[]; count: number }>(`/monitoring/trades?limit=${limit}`),
  getMonitorRounds: (limit = 50) =>
    request<{ rounds: any[]; count: number }>(`/monitoring/rounds?limit=${limit}`),
  getStrategyStatus: () =>
    request<{ status: any; orders: any[]; count: number }>("/monitoring/strategy"),
  getGridStatus: () =>
    request<any>("/monitoring/grid"),
  runGrid: () =>
    request<{ ok: boolean; grid_mode?: string; confidence?: number; reason?: string; error?: string }>("/monitoring/grid/run", { method: "POST" }),
  getGridHistory: (limit = 30) =>
    request<{ signals: any[]; count: number }>(`/monitoring/grid-history?limit=${limit}`),

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
  runArbitrage: (config: any) =>
    request<any>('/arbitrage/run', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  applyBestParams: () =>
    request<{ applied: boolean }>('/optimize/best-params', {
      method: 'POST',
    }),

  runResearch: (cfg: Record<string, any>) =>
    request<{ task_id: string }>('/research/run', { method: 'POST', body: JSON.stringify(cfg) }),
  getResearchResults: (id: string) =>
    request<ResearchResult>(`/research/results/${id}`),

  // ── Admin / Operator panel ──
  getAdminOverview: () =>
    request<AdminOverview>('/admin/overview'),
  getWatchlist: () =>
    request<MonitoredSymbol[]>('/admin/watchlist'),
  addWatchlist: (item: Partial<MonitoredSymbol>) =>
    request<MonitoredSymbol>('/admin/watchlist', { method: 'POST', body: JSON.stringify(item) }),
  removeWatchlist: (symbol: string) =>
    request<{ ok: boolean }>(`/admin/watchlist?symbol=${encodeURIComponent(symbol)}`, { method: 'DELETE' }),
  toggleWatchlistPin: (symbol: string) =>
    request<{ ok: boolean }>(`/admin/watchlist/pin?symbol=${encodeURIComponent(symbol)}`, { method: 'POST' }),
  getCredentials: () =>
    request<CredentialStatus[]>('/admin/credentials'),
  getTaskHistory: (limit = 200) =>
    request<TaskHistoryItem[]>(`/admin/tasks?limit=${limit}`),
  getUsage: () =>
    request<UsageStat[]>('/admin/usage'),
  getSiteConfig: () =>
    request<SiteConfig>('/admin/config'),
  updateSiteConfig: (patch: Partial<SiteConfigUpdate>) =>
    request<SiteConfig>('/admin/config', { method: 'PATCH', body: JSON.stringify(patch) }),
  getLlmModel: () =>
    request<SiteConfig>('/admin/config').then((c: SiteConfig) => c.llm_model),
  setLlmModel: (model: string) =>
    request<SiteConfig>('/admin/config', { method: 'PATCH', body: JSON.stringify({ llm_model: model }) }),

  // ── Experiments (Qlib-style Recorder) ──
  listExperiments: (kind?: string) =>
    request<any>(`/experiments${kind ? `?kind=${kind}` : ''}`),
  getExperiment: (id: string) => request<any>(`/experiments/${id}`),
  compareExperiments: (ids: string[]) =>
    request<any>('/experiments/compare', { method: 'POST', body: JSON.stringify({ ids }) }),

  // ── Indicator validation (TV vs engine) ──
  validateIndicator: (payload: { symbol: string; timeframe: string; source: string; name: string; period: number; reference: number[] }) =>
    request<any>('/validate/indicator', { method: 'POST', body: JSON.stringify(payload) }),
  pushBacktestToNotion: (payload: { task_id: string; symbol: string; strategy: string; timeframe: string }) =>
    request<{ ok: boolean; notion_configured: boolean }>('/backtest/push-notion', { method: 'POST', body: JSON.stringify(payload) }),

  // ── Trades (BingX auto journal, persisted on GitHub) ──
  getTrades: () => request<any>('/trades'),
  getArbTrades: () => request<any>('/trades/arb'),
  getPredictTrades: () => request<any>('/trades/predict'),
};
export default api;
