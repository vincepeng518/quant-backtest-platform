"""scripts/realtime_test.py — 驗證 BingX WS 實時 K 線 → 模擬掛單履約 < 0.2s。

每串接一個頻道記錄:延遲、狀態、下一個頻道。
用法: python3.12 scripts/realtime_test.py [--ticks 20] [--symbol BTC-USDT]
"""
import argparse, asyncio, logging, sys, time
sys.path.insert(0, "/root/quant-backtest-platform")
from engine.realtime import RealtimeKlineFeed

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

CHANNELS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]  # 依序串接的頻道


async def run_channel(symbol: str, n_ticks: int) -> dict:
    """串接一個頻道:symbol 的實時 kline,收集 n_ticks 筆模擬撮合延遲。"""
    t0 = time.perf_counter()
    feed = RealtimeKlineFeed(symbol=symbol, timeframe="1m")
    try:
        await asyncio.wait_for(feed.run(n_ticks=n_ticks), timeout=60)
        lat = [m["latency_ms"] for m in feed.ex.matches]
        lat_sorted = sorted(lat)
        p95 = lat_sorted[int(len(lat_sorted) * 0.95)] if lat_sorted else None
        wall = time.perf_counter() - t0
        return {
            "channel": f"{symbol}@kline_1m",
            "status": "ok",
            "n_matches": len(lat),
            "avg_ms": round(sum(lat) / len(lat), 4) if lat else None,
            "p95_ms": round(p95, 4) if p95 is not None else None,
            "within_200ms_all": all(m["within_200ms"] for m in feed.ex.matches) if lat else None,
            "wall_sec": round(wall, 3),
            "reconnects": len(feed.disconnect_logs),
        }
    except Exception as e:
        return {
            "channel": f"{symbol}@kline_1m",
            "status": "error",
            "error": f"{type(e).__name__}: {str(e)[:200]}",
            "disconnect_logs": feed.disconnect_logs,
        }


async def main(ticks: int, max_channel: int) -> int:
    print(f"=== 實時 K 線模擬掛單履約驗證(目標 <0.2s) ===\n串接頻道(依序): {CHANNELS[:max_channel]}\n")
    results = []
    for i, sym in enumerate(CHANNELS[:max_channel]):
        # 「下一個頻道」連帶上一頻道結果一起顯示(任務要求)
        res = await run_channel(sym, ticks)
        results.append(res)
        nxt = CHANNELS[i + 1] if i + 1 < max_channel else "(無,結束)"
        status = "✅" if res["status"] == "ok" else "❌"
        print(f"{status} 頻道[{res['channel']}] status={res['status']} "
              f"| 撮合{res.get('n_matches','-')}筆 avg={res.get('avg_ms','-')}ms "
              f"p95={res.get('p95_ms','-')}ms 全部<200ms={res.get('within_200ms_all','-')} "
              f"外徑{res.get('wall_sec','-')}s 重連={res.get('reconnects',0)}")
        if res["status"] == "error":
            print(f"   !! {res.get('error')}")
            for l in res.get("disconnect_logs", []):
                print(f"   LOG: {l}")
        else:
            print(f"   下一頻道: {nxt}")
    # 總結
    ok = [r for r in results if r.get("within_200ms_all")]
    print(f"\n=== 總結: {len(ok)}/{len(results)} 頻道達成全部撮合 <200ms ===")
    return 0 if len(ok) == len(results) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=20, help="每個頻道收集幾筆模擬撮合")
    ap.add_argument("--channels", type=int, default=1, choices=[1, 2, 3])
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.ticks, args.channels)))
