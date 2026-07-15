import { StrategyConfig, RiskParams, FundingConfig, PerpetualConfig, ExchangeConfig } from './strategy';

export interface BacktestConfig {
  strategy: StrategyConfig;
  symbol: string;
  timeframe: string;
  source?: string;
  start_date?: string;
  end_date?: string;
  // Capital / cost (top-level — backend BacktestConfig shape)
  initial_capital: number;
  commission: number;
  slippage: number;
  max_position_pct?: number;
  // Engine realism (opt-in; disabled = identical to legacy 1x spot)
  funding?: FundingConfig;
  perpetual?: PerpetualConfig;
  exchange?: ExchangeConfig;
}

export interface TradeRecord {
  trade_id: number;
  entry_time: number;
  exit_time: number;
  direction: 'long' | 'short';
  entry_price: number;
  exit_price: number;
  quantity: number;
  pnl: number;
  pnl_pct: number;
  commission: number;
  holding_bars: number;
  exit_reason: string;
}

export interface PerformanceMetrics {
  total_return: number;
  total_return_pct: number;
  annual_return: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  max_drawdown_duration: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  avg_win: number;
  avg_loss: number;
  avg_holding_bars: number;
  expectancy: number;
  calmar_ratio: number;
  volatility: number;
  // ── Pine v6 alignment (emitted by backend; optional for backward compat) ──
  net_profit?: number;
  largest_loss?: number;
  largest_loss_pct?: number;
  largest_win?: number;
  win_loss_ratio?: number;
  annual_return_pct?: number;
  trade_freq?: number;
}

export interface EquityPoint {
  timestamp: number;
  time: number;
  equity: number;
  drawdown: number;
}

export interface PositionStatusPoint {
  time: number | string;
  state: 'long' | 'short' | 'flat' | string;
}

export interface BacktestResult {
  task_id: string;
  config: BacktestConfig;
  metrics: PerformanceMetrics;
  equity_curve: EquityPoint[];
  buy_hold_equity: EquityPoint[];
  trades: TradeRecord[];
  position_status?: PositionStatusPoint[];
}

export interface StrategyParam {
  name: string;
  type: 'number' | 'string' | 'boolean';
  default: number | string | boolean;
  description?: string;
}

export interface StrategyTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  code: string;
  params: StrategyParam[];
}

export interface UserStrategy {
  id: string;
  name: string;
  description: string;
  category: string;
  code: string;
  created_at: number;
  updated_at: number;
}

export interface StrategyPayload {
  name: string;
  description: string;
  category: string;
  code: string;
}

export interface AnalysisResult {
  task_id: string;
  status: string;
  type: string;
  summary: {
    // walk-forward
    avg_oos_sharpe?: number;
    avg_oos_return?: number;
    sharpe_std?: number;
    return_std?: number;
    consistency?: number;
    windows?: Array<Record<string, any>>;
    // monte-carlo
    bankruptcy_prob?: number;
    expected_return?: number;
    var_95?: number;
    cvar_95?: number;
    percentiles?: Record<string, number>;
    max_drawdowns?: number[];
  };
}

export interface OptimizeGrid {
  param_x: string;
  param_y: string;
  x_values: number[];
  y_values: number[];
  scores: (number | null)[][];
}

export interface OptimizeResult {
  task_id: string;
  status: string;
  best_params: Record<string, any>;
  best_score: number;
  trials: { params: Record<string, any>; score: number }[];
  grid: OptimizeGrid | null;
}

export interface MonitorStats {
  available: boolean;
  updated_at?: string;
  data?: {
    shadow: { total: number; resolved: number; wins: number; win_rate: number; avg_pnl: number; total_pnl: number };
    tail: { rounds: number; avg_jump_last10s_pct: number; avg_jump_prev10s_pct: number; tail_accel: number };
    hypothesis: { up_win_rate: number; down_win_rate: number; note: string };
  };
}

// ── Admin / Operator panel ──
export interface CredentialStatus {
  name: string;
  kind: string;
  configured: boolean;
  masked_value: string;
  updated_at?: string | null;
}

export interface MonitoredSymbol {
  symbol: string;
  market: string;
  exchange?: string;
  description?: string;
  pinned: boolean;
  added_at: string;
}

export interface TaskHistoryItem {
  task_id: string;
  kind: string;
  status: string;
  created_at: string;
  symbol?: string | null;
  timeframe?: string | null;
  strategy?: string | null;
  score?: number | null;
  detail: string;
}

export interface UsageStat {
  metric: string;
  value: number;
}

export interface SiteConfig {
  default_timeframe: string;
  default_symbol: string;
  default_source: string;
  default_initial_capital: number;
  default_commission: number;
  default_slippage: number;
  max_position_pct: number;
  risk_guard_daily_loss_pct: number;
  risk_guard_max_drawdown_pct: number;
  maintenance_mode: boolean;
  updated_at: string;
}

export interface AdminOverview {
  watchlist: MonitoredSymbol[];
  credentials: CredentialStatus[];
  task_history: TaskHistoryItem[];
  usage: UsageStat[];
  config: SiteConfig;
}

export interface ResearchResult {
  task_id: string;
  status: string;
  summary: {
    returns_stats?: Record<string, number>;
    autocorrelation?: Record<string, number>;
    hurst?: number;
    vol_regime?: { windows: Array<{ i: number; vol: number; regime: string }>; q_high: number; q_low: number };
    correlation?: number | null;
    seasonality?: Record<string, number>;
    signal_counts?: Record<string, number>;
    long_short_ratio?: number;
    entry_timing?: { mean_percentile: number; samples: number };
    signal_forward_return?: { mean: number; n: number };
  };
}
