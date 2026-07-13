"""Phase 1-4 監聽 + 影子交易系統入口。

用法:
  # 即時監聽 (Binance WS -> 引擎 -> SQLite)
  python3 -m monitoring.run --live --db shadow.db

  # 歷史回放驗證 (用 Binance 1m 數據餵引擎, 驗證影子記錄/結算)
  python3 -m monitoring.run --replay BTC/USDT --db shadow.db

註: 訂單簿源目前接 Polymarket CLOB (深度代理)。
     TODO: 替換為 predict.fun BNB Chain CLOB endpoint (主戰場)。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from monitoring.shadow_engine import ShadowEngine, PhaseConfig
from monitoring.feed_binance import BinanceWsFeed
from monitoring.orderbook import PolymarketClobSource


# TODO: 替換為你的 predict.fun 目標市場 token id (或從 config 讀)
POLY_TOKEN_ID = "98022490269692409998126496127597032490334070080325855126491859374983463996227"


def build_engine(db: str, live_book: bool) -> ShadowEngine:
    book = PolymarketClobSource(POLY_TOKEN_ID) if live_book else None
    return ShadowEngine(db, cfg=PhaseConfig(), book_source=book)


async def run_live(db: str) -> None:
    eng = build_engine(db, live_book=True)
    feed = BinanceWsFeed("btcusdt@trade")
    feed.on_tick(lambda price, ts: eng.on_spot(price, ts, market="BTC-5m"))
    print("[LIVE] Binance WS -> ShadowEngine started. db=", db)
    try:
        await feed.run()
    except KeyboardInterrupt:
        pass
    finally:
        eng.close()


async def run_replay(symbol: str, db: str) -> None:
    """用 Binance 1m 歷史數據按秒展開餵引擎 (近似監聽), 驗證 4 階段邏輯。"""
    from data.providers.binance import BinanceProvider
    eng = build_engine(db, live_book=False)
    p = BinanceProvider()
    df = await p.fetch_ohlcv(symbol, "1m", limit=300)
    await p.close()
    print(f"[REPLAY] feeding {len(df)} 1m bars -> engine")
    for _, r in df.iterrows():
        # 用收盤價當作該分鐘的現價快照, ts 用 timestamp + 隨機秒偏移模擬
        import time
        ts = r["timestamp"].timestamp()
        eng.on_spot(float(r["close"]), ts, market="BTC-5m")
    # 結算: 用下一根收盤當作輪次結算價 (近似)
    print("[REPLAY] done. shadow_trades recorded:",
          eng.conn.execute("SELECT COUNT(*) FROM shadow_trades").fetchone()[0])
    eng.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="即時監聽模式")
    ap.add_argument("--replay", metavar="SYMBOL", help="歷史回放 (e.g. BTC/USDT)")
    ap.add_argument("--db", default="shadow.db")
    args = ap.parse_args()
    if args.live:
        asyncio.run(run_live(args.db))
    elif args.replay:
        asyncio.run(run_replay(args.replay, args.db))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
