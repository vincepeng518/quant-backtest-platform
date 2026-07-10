import { create } from 'zustand';
import { SymbolInfo, ChartData } from '@/types/chart';

interface DataStore {
  symbols: SymbolInfo[];
  selectedSymbol: string;
  ohlcv: ChartData[];
  loading: boolean;
  loadSymbols: () => Promise<void>;
  loadOHLCV: (symbol: string, timeframe: string) => Promise<void>;
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
  loadOHLCV: async (symbol, timeframe) => {
    set({ loading: true });
    try {
      const res = await fetch(`/api/data/ohlcv?symbol=${symbol}&timeframe=${timeframe}`);
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
