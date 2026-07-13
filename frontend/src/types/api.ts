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
}

export interface EquityPoint {
  timestamp: number;
  time: number;
  equity: number;
  drawdown: number;
}

export interface BacktestResult {
  task_id: string;
  config: BacktestConfig;
  metrics: PerformanceMetrics;
  trades: TradeRecord[];
  equity_curve: EquityPoint[];
  buy_hold_equity: EquityPoint[];
  monthly_returns: Record<string, number>;
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
