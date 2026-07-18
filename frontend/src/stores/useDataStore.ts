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
  if (/^(NCCO|NCFX|NCSI|NCSK)/.test(symbol.toUpperCase())) return 'bingx_tradfi';
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
      let base: SymbolInfo[] = [];
      if (res.ok) {
        base = await res.json();
      }
      // Merge BingX TradFi symbols (with live status) so they show up in the picker
      let tradfi: SymbolInfo[] = [];
      try {
        const r2 = await fetch('/api/exchanges/tradfi-symbols');
        if (r2.ok) {
          const j = await r2.json();
          tradfi = (j.symbols || []).map((s: any) => ({
            symbol: s.symbol,
            market: 'tradfi' as const,
            exchange: 'bingx',
            status: s.status,
            category: s.category,
            description: s.name,
          }));
        }
      } catch { /* tradfi endpoint optional */ }
      // dedup by symbol (tradfi wins for status/category)
      const seen = new Set(base.map((s) => s.symbol));
      const merged = [...base, ...tradfi.filter((s) => !seen.has(s.symbol))];
      set({ symbols: merged, selectedSymbol: merged[0]?.symbol || '' });
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
