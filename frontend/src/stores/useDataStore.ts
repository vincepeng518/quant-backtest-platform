import { create } from 'zustand';
import { SymbolInfo, ChartData } from '@/types/chart';

interface DataStore {
  symbols: SymbolInfo[];
  selectedSymbol: string;
  ohlcv: ChartData[];
  loading: boolean;
  loadSymbols: () => Promise<void>;
  loadOHLCV: (symbol: string, timeframe: string, source?: string) => Promise<void>;
}

// TradFi symbols (yfinance) — 这些不走 BingX，需带 source=tradfi
const TRADFI_RE = /[=]|^-USD|USD-|^[A-Z]{3}=|GC=F|SI=F|CL=F|BTC-USD|SPY|QQQ|DIA|AAPL|TSLA|NVDA|MSFT|AMZN|META|GOOGL/i;

export function resolveSource(symbol: string, market?: string): string {
  if (market === 'tradfi') return 'tradfi';
  if (TRADFI_RE.test(symbol)) return 'tradfi';
  return 'bingx';
}

export const useDataStore = create<DataStore>((set) => ({
  symbols: [],
  selectedSymbol: '',
  ohlcv: [],
  loading: false,
  loadSymbols: async () => {
    try {
      const res = await fetch('/api/data/symbols');
      if (res.ok) {
        const symbols = await res.json();
        set({ symbols, selectedSymbol: symbols[0]?.symbol || '' });
      }
    } catch (e) {
      console.error(e);
    }
  },
  loadOHLCV: async (symbol, timeframe, source) => {
    set({ loading: true });
    try {
      const src = source ?? resolveSource(symbol);
      const res = await fetch(`/api/data/ohlcv?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&source=${src}`);
      if (res.ok) {
        const ohlcv = await res.json();
        set({ ohlcv });
      }
    } catch (e) {
      console.error(e);
    } finally {
      set({ loading: false });
    }
  },
}));
