// 币種分類目錄：用於 SymbolSearch 的板塊篩選。
// BingX load_markets 只給 symbol，不給板塊，這裡用手動維護的常用分類表。
// 只列主流/有代表性的；未列出的 symbol 歸入「其他」，仍可自由搜尋。

export type Sector = '主流' | 'Meme' | 'DeFi' | 'AI' | 'Layer2' | 'TradFi' | '其他';

export const SECTOR_GROUPS: Record<Exclude<Sector, '其他'>, string[]> = {
  主流: [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT',
    'DOGE/USDT', 'TRX/USDT', 'AVAX/USDT', 'DOT/USDT', 'LTC/USDT', 'LINK/USDT',
    'TON/USDT', 'MATIC/USDT', 'NEAR/USDT', 'ATOM/USDT', 'UNI/USDT', 'ETC/USDT',
    'XLM/USDT', 'BCH/USDT', 'FIL/USDT', 'ICP/USDT', 'APT/USDT', 'SUI/USDT',
    'ARB/USDT', 'OP/USDT', 'INJ/USDT', 'TIA/USDT', 'SEI/USDT', 'RNDR/USDT',
  ],
  Meme: [
    'PEPE/USDT', 'WIF/USDT', 'SHIB/USDT', 'DOGE/USDT', 'FLOKI/USDT', 'BONK/USDT',
    'MEME/USDT', 'BOME/USDT', 'SLERF/USDT', 'BRETT/USDT', 'POPCAT/USDT', 'MOG/USDT',
  ],
  DeFi: [
    'UNI/USDT', 'AAVE/USDT', 'MKR/USDT', 'LDO/USDT', 'CRV/USDT', 'COMP/USDT',
    'SNX/USDT', 'CAKE/USDT', 'DYDX/USDT', 'GMX/USDT', 'PENDLE/USDT', 'JUP/USDT',
  ],
  AI: [
    'FET/USDT', 'RNDR/USDT', 'AGIX/USDT', 'OCEAN/USDT', 'TAO/USDT', 'WLD/USDT',
    'AKT/USDT', 'GRT/USDT', 'ROSE/USDT', 'NMR/USDT',
  ],
  Layer2: [
    'ARB/USDT', 'OP/USDT', 'MATIC/USDT', 'IMX/USDT', 'STRK/USDT', 'MANTA/USDT',
    'METIS/USDT', 'ZK/USDT', 'BLAST/USDT',
  ],
  TradFi: [
    'AAPL', 'TSLA', 'NVDA', 'MSFT', 'AMZN', 'META', 'GOOGL', 'SPY', 'QQQ', 'DIA',
    'EURUSD=X', 'USDJPY=X', 'GC=F', 'SI=F', 'CL=F', 'BTC-USD',
    'NCCOXAG2USD/USDT', 'NCCOXPT2USD/USDT', 'NCCOPALLADIUM2USD/USDT',
    'NCCO724COPPER2USD/USDT', 'NCCO1OILBRENT2USD/USDT', 'NCCO1OILWTI2USD/USDT',
    'NCCOHEATINGOIL2USD/USDT', 'NCCOGOLD2USD/USDT', 'NCCOXAUEUR2USD/USDT',
    'NCFXAUD2USD/USDT', 'PAXG/USDT', 'XAUT/USDT',
  ],
};

// symbol -> sector 反查表
export const SYMBOL_SECTOR: Record<string, Sector> = (() => {
  const m: Record<string, Sector> = {};
  (Object.keys(SECTOR_GROUPS) as Exclude<Sector, '其他'>[]).forEach((sec) => {
    SECTOR_GROUPS[sec].forEach((s) => {
      m[s] = sec;
    });
  });
  return m;
})();

export function sectorOf(symbol: string): Sector {
  return SYMBOL_SECTOR[symbol] ?? '其他';
}
