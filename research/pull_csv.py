"""pull_csv.py — 全部走 BingX (優先)。
- 加密 (BTC/ETH/SOL/HYPE): ccxt bingx()
- TradFi (GOLD): BingXTradFiProvider (NCCOGOLD2USD-USDT)
週期: 15m/30m/1h/4h/1d (BingX 不支援 45m)
存: data/csv/<SYM>_<TF>.csv (覆蓋既有)
"""
from __future__ import annotations
import os, sys, asyncio
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ccxt
from data.providers.bingx_tradfi import BingXTradFiProvider

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(PROJ, "data", "csv")
os.makedirs(CSV_DIR, exist_ok=True)

CRYPTO = [("BTC/USDT", "BTC_USDT"), ("ETH/USDT", "ETH_USDT"), ("SOL/USDT", "SOL_USDT"),
          ("HYPE/USDT", "HYPE_USDT"), ("XRP/USDT", "XRP_USDT"), ("AVAX/USDT", "AVAX_USDT"),
          ("ZRO/USDT", "ZRO_USDT"), ("RUNE/USDT", "RUNE_USDT"), ("WIF/USDT", "WIF_USDT"),
          ("ATOM/USDT", "ATOM_USDT"), ("DYDX/USDT", "DYDX_USDT")]
TFS = ["15m", "30m", "1h", "4h", "1d"]
LIMIT = 1500  # BingX 單次上限; 如需更長再分段

async def main(symbol: str | None = None, tf: str | None = None):
    syms = [(s, t) for (s, t) in CRYPTO if symbol is None or t == symbol]
    tfs = [tf] if tf else TFS
    ex = ccxt.bingx()
    # 1) 加密貨幣 via ccxt
    for sym, tag in syms:
        for tf in tfs:
            fname = f"{tag}_{tf}.csv"
            fpath = os.path.join(CSV_DIR, fname)
            try:
                ohlcv = ex.fetch_ohlcv(sym, tf, limit=LIMIT)
                if not ohlcv:
                    print(f"FAIL {sym} {tf}")
                    continue
                df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                df.to_csv(fpath, index=False)
                print(f"OK {fname} bars={len(df)}")
            except Exception as e:
                print(f"FAIL {sym} {tf}: {str(e)[:50]}")
    # 2) GOLD via TradFi
    if symbol is None or symbol == "GOLD_USDT":
        tradfi = BingXTradFiProvider()
        for tf in tfs:
            fname = f"GOLD_USDT_{tf}.csv"
            fpath = os.path.join(CSV_DIR, fname)
            try:
                df = await tradfi.fetch_ohlcv("NCCOGOLD2USD-USDT", tf, limit=1000)
                if df is None or len(df) == 0:
                    print(f"FAIL GOLD {tf}")
                    continue
                df.to_csv(fpath, index=False)
                print(f"OK {fname} bars={len(df)}")
            except Exception as e:
                print(f"FAIL GOLD {tf}: {str(e)[:50]}")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=None, help="單幣種 tag, 如 BTC_USDT (不帶 _TF)")
    ap.add_argument("--tf", default=None, help="單週期, 如 1h")
    args = ap.parse_args()
    asyncio.run(main(args.symbol, args.tf))
