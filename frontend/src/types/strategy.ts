import { MarketType } from './chart';

export interface ParamSpec {
  name: string;
  label: string;
  type: 'int' | 'float' | 'bool' | 'string' | 'select';
  default: any;
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
  description?: string;
}

export interface StrategyTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  params: ParamSpec[];
  supports_custom_code?: boolean;
}

export interface StrategyConfig {
  template_id: string;
  params: Record<string, any>;
  custom_code?: string;
}

export interface RiskParams {
  initial_capital: number;
  commission: number;
  slippage: number;
  max_position_pct: number;
  stop_loss?: number;
  take_profit?: number;
}
