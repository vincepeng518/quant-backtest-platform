export type MarketType = 'crypto' | 'stock' | 'futures' | 'forex' | 'tradfi';
export type Timeframe = '1m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1d' | '1w';

export interface SymbolInfo {
  symbol: string;
  market: MarketType;
  exchange?: string;
  baseAsset?: string;
  quoteAsset?: string;
  description?: string;
}

export interface OHLCV {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ChartData extends OHLCV {
  time: number; // For lightweight charts
}

export interface TradeMarker {
  time: number;
  position: 'aboveBar' | 'belowBar' | 'inBar';
  color: string;
  shape: 'arrowUp' | 'arrowDown' | 'circle';
  text: string;
}

export interface IndicatorLine {
  name: string;
  data: { time: number; value: number }[];
  color: string;
}
