"""Phase 1-4 監聽 + 影子交易系統入口 (穩健版)。

用法:
  # 即時監聽 (Binance WS -> 引擎 -> SQLite, 自動結算, 無人值守)
  python3 -m monitoring.run --live

  # 歷史回放驗證 (Binance 1m 數據餵引擎)
  python3 -m monitoring.run --replay BTC/USDT

  # 自檢 (跑單元邏輯確認管線通)
  python3 -m monitoring.run --selftest

註: 訂單簿源預設 polymarket CLOB (深度代理)。
     predict.fun BNB Chain CLOB 需 auth, 配置 orderbook.source=polygon 以外時需另行授權。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from monitoring.config import MonitorConfig
from monitoring.shadow_engine import ShadowEngine
from monitoring.feed_binance import BinanceWsFeed
from monitoring.orderbook import PredictFunBookSource


def setup_logging(log_path: str) -> None:
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )


def build_book(cfg: MonitorConfig):
    # 主战场: predict.fun GraphQL 订单簿 (公开, 无需 auth)
    if cfg.ob_source in ("predictfun", "polymarket"):
        return PredictFunBookSource()
    return None


async def run_live(cfg: MonitorConfig) -> None:
    setup_logging(cfg.log)
    # Phase 1 真值源: predict.fun REST (API Key) 的輪次 startPrice
    target_provider = None
    if cfg.api_key:
        from monitoring.predictfun import PredictFunRest
        _rest = PredictFunRest(cfg.api_key)
        target_provider = _rest.start_price_for
    eng = ShadowEngine(cfg, book_source=build_book(cfg), target_provider=target_provider)
    feed = BinanceWsFeed(cfg.binance_symbol)
    # 动态解析当前活跃的 predict.fun BTC Up/Down 轮次 id
    from monitoring.predictfun import PredictFunSource
    pfs = PredictFunSource()

    def get_market_id():
        try:
            rs = pfs.active_btc_rounds(limit=80)
            if rs:
                return rs[0]["id"]  # 最近活跃轮次
        except Exception:
            pass
        return "BTC-5m"  # fallback

    current_mid = [get_market_id()]

    def on_tick(price, ts):
        mid = current_mid[0]
        eng.on_spot(price, ts, market=mid)
        # 每 ~30s 重新解析活跃轮次 (轮次会轮替)
        if int(ts) % 30 == 0:
            nm = get_market_id()
            if nm != mid:
                current_mid[0] = nm
                logging.info("[LIVE] switched market -> %s", nm)

    feed.on_tick(on_tick)
    logging.info("[LIVE] start. db=%s book=%s market=%s", cfg.db, cfg.ob_source, current_mid[0])

    # 背景任務: 每 60s 把監控統計推送到回測平台後端 (首頁展示用)
    push_task = asyncio.create_task(_push_loop(cfg))

    # 自愈重連: WS / GraphQL 任一網路中斷不該讓守護進程靜默死掉
    backoff = 1
    while True:
        try:
            await feed.run()
            break  # feed.run() 正常返回 (極少見) -> 退出
        except asyncio.CancelledError:
            raise
        except KeyboardInterrupt:
            logging.info("[LIVE] stopped by user")
            break
        except Exception as e:
            logging.error("[LIVE] feed crashed: %s — reconnect in %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)  # 指數退避上限 60s
            # 重新建一個 feed（舊的可能已壞）
            try:
                feed = BinanceWsFeed(cfg.binance_symbol)
                feed.on_tick(on_tick)
            except Exception:
                pass
    try:
        push_task.cancel()
        await push_task
    except Exception:
        pass
    eng.close()
    try:
        pfs.close()
    except Exception:
        pass


async def _push_loop(cfg: MonitorConfig) -> None:
    """定時把 review() 摘要推送到回測平台後端 /api/monitoring/push。"""
    from monitoring.review import review
    backend = os.getenv("MONITOR_BACKEND_URL",
                        "https://affectionate-alignment-production-6d7e.up.railway.app")
    key = os.getenv("MONITOR_PUSH_KEY", "quant-monitor-local")
    import httpx
    while True:
        try:
            await asyncio.sleep(60)
            rep = review(cfg.db)
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.post(
                    f"{backend}/api/monitoring/push",
                    headers={"x-monitor-key": key},
                    json=rep,
                )
                if r.status_code == 200:
                    logging.info("[PUSH] monitoring stats pushed (resolved=%s)",
                                 rep.get("shadow", {}).get("resolved"))
                else:
                    logging.warning("[PUSH] failed %s: %s", r.status_code, r.text[:80])
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.warning("[PUSH] loop error: %s", e)
            await asyncio.sleep(30)


async def run_replay(cfg: MonitorConfig, symbol: str) -> None:
    setup_logging(cfg.log)
    from data.providers.binance import BinanceProvider
    eng = ShadowEngine(cfg, book_source=None)
    p = BinanceProvider()
    df = await p.fetch_ohlcv(symbol, "1m", limit=300)
    await p.close()
    if df is None:
        logging.error("fetch failed")
        return
    logging.info("[REPLAY] feeding %d bars", len(df))
    for _, r in df.iterrows():
        ts = r["timestamp"].timestamp()
        eng.on_spot(float(r["close"]), ts, market="BTC-5m")
    logging.info("[REPLAY] done. stats=%s", eng.stats())
    eng.close()


def run_selftest(cfg: MonitorConfig) -> None:
    """不依賴網路: 用合成 tick 驗證 4 階段管線。"""
    setup_logging(cfg.log)
    tmp_db = cfg.db + ".selftest"
    if os.path.exists(tmp_db):
        os.remove(tmp_db)
    if os.path.exists(tmp_db + "-wal"):
        os.remove(tmp_db + "-wal")
    if os.path.exists(tmp_db + "-shm"):
        os.remove(tmp_db + "-shm")
    cfg.db = tmp_db
    cfg.settle_on_close = False  # 手動結算驗證
    eng = ShadowEngine(cfg, book_source=None)
    base = 64000.0
    # 平穩基線
    for i in range(60):
        eng.on_spot(base, 300 + i, market="T")
    # 窗口內砸盤 -> 應觸發 UP 信號
    eng.on_spot(base - 30, 420, market="T")
    # 尾盤窗口
    for i in range(80):
        eng.on_spot(base, 520 + i, market="T")
    # 結算
    eng.settle_round("T:1", base + 5)
    s = eng.stats()
    logging.info("[SELFTEST] %s", s)
    eng.close()
    assert s["shadow_trades"] >= 1, "selftest: no signal"
    assert s["tail_snapshots"] >= 1, "selftest: no tail"
    print("SELFTEST OK:", s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--replay", metavar="SYMBOL")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--review", action="store_true", help="Phase 4 自動覆盤報告 (從 DB)")
    ap.add_argument("--config", default="monitoring/config.yaml")
    args = ap.parse_args()
    cfg = MonitorConfig.load(args.config)
    if args.live:
        asyncio.run(run_live(cfg))
    elif args.replay:
        asyncio.run(run_replay(cfg, args.replay))
    elif args.selftest:
        run_selftest(cfg)
    elif args.review:
        from monitoring.review import review
        import json
        print(json.dumps(review(cfg.db), indent=2, ensure_ascii=False))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
