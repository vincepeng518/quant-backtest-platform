import { StrategyConfig, RiskParams } from './strategy';

export interface BacktestConfig {
  strategy: StrategyConfig;
  symbol: string;
  timeframe: string;
  from: number;
  to: number;
  risk: RiskParams;
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
