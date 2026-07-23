"""
Trade Bot — 自動抓取 BingX 交易數據並永久寫入 GitHub。

抓取來源 (ccxt, 避開 allOrders 限流):
  - fetch_positions()   : 當前持倉 (開倉價/槓桿/未實現盈虧/清算價)
  - fetch_my_trades()   : 歷史成交 (逐 symbol, 含 positionSide/side/price/amount)

配對邏輯:
  同 (symbol, positionSide) 分組, 按時間排序:
  - LONG:  BUY=開倉, SELL=平倉
  - SHORT: SELL=開倉, BUY=平倉
  FIFO 配對 → 每筆 round-trip 含 entry/exit/PnL

永久儲存: GitHub repo trades/ 目錄 (git-tracked)

用法:
  python bot/trade_bot.py            # 抓一次, 寫一筆快照
  python bot/trade_bot.py --daemon   # 每 300s 跑一次
"""
from __future__ import annotations
import os, sys, time, json, argparse, logging, base64, urllib.request
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("trade_bot")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from app.services.strategy_git import REPO  # type: ignore
except Exception:
    REPO = "vincepeng518/quant-backtest-platform"

try:
    import ccxt
except Exception as e:
    logger.warning("ccxt import failed: %s", e)
    ccxt = None

TRADES_PREFIX = "trades"

# 用戶已知交易 symbol (ccxt 格式)
KNOWN_SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XMR/USDT:USDT",
    "BCH/USDT:USDT", "LDO/USDT:USDT", "JTO/USDT:USDT", "VIRTUAL/USDT:USDT",
    "LONGXIA/USDT:USDT",
    # TradFi
    "NCCOGOLD2USD/USDT:USDT", "NCSINASDAQ1002USD/USDT:USDT",
    "NCFXEUR2USD/USDT:USDT", "NCFXGBP2USD/USDT:USDT",
    "NCCO1OILWTI2USD/USDT:USDT",
]


def simplify_symbol(raw: str | None) -> str | None:
    """BingX symbol 簡化: BTC-USDT→BTC, NCCOGOLD2USD-USDT→GOLD, NCFXEUR2USD-USDT→EUR/USD"""
    if not raw:
        return raw
    import re
    s = raw.strip().replace("/", "-").replace(":USDT", "").replace(":USDC", "")
    m = re.match(r"^NCFX(\w+?)2(\w+)-USDT$", s)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.match(r"^NC(CO|SK|SI)\d*(.+?)2USD-USDT$", s)
    if m:
        return m.group(2)
    m = re.match(r"^NC(\w+)-USDT$", s)
    if m:
        return m.group(1)
    if s.endswith("-USDT"):
        return s[:-len("-USDT")]
    return s


def _client():
    if ccxt is None:
        return None
    return ccxt.bingx({
        "apiKey": os.environ.get("BINGX_API_KEY", ""),
        "secret": os.environ.get("BINGX_API_SECRET", ""),
        "enableRateLimit": True,
    })


def fetch_positions(ex) -> list:
    """當前持倉 → OPEN records"""
    try:
        raw = ex.fetch_positions()
    except Exception as e:
        logger.warning("fetch_positions err: %s", e)
        return []
    out = []
    for p in raw:
        sym = simplify_symbol(p.get("symbol"))
        side = (p.get("side") or "").upper()
        avg = float(p.get("entryPrice") or 0)
        if not sym or avg <= 0:
            continue
        lev = float(p.get("leverage") or 0)
        if lev > 20:
            logger.warning("高槓桿 %s %sx", sym, lev)
        out.append({
            "symbol": sym,
            "side": side,
            "positionAmt": float(p.get("contracts") or p.get("amount") or 0),
            "avgPrice": avg,
            "exitPrice": 0.0,
            "leverage": lev,
            "unrealizedProfit": float(p.get("unrealizedPnl") or 0),
            "realizedProfit": 0.0,
            "pnlRatio": 0.0,
            "positionValue": float(p.get("notional") or 0),
            "liquidationPrice": float(p.get("liquidationPrice") or 0),
            "status": "OPEN",
            "ts": int(time.time() * 1000),
        })
    return out


def fetch_all_trades(ex, symbols: list[str]) -> list[dict]:
    """逐 symbol 抓 fetchMyTrades, 合併所有成交"""
    all_trades = []
    for sym in symbols:
        try:
            trades = ex.fetch_my_trades(sym, limit=200)
            all_trades.extend(trades)
            logger.info("  %s: %d trades", sym, len(trades))
        except Exception as e:
            err = str(e)
            if "100410" in err:
                logger.warning("  %s: rate limited, skip", sym)
            elif "does not have" in err or "not found" in err.lower():
                pass  # symbol not traded
            else:
                logger.warning("  %s: %s", sym, err[:100])
            continue
        time.sleep(0.3)  # rate limit buffer
    return all_trades


def pair_trades(trades: list[dict]) -> tuple[list[dict], float]:
    """FIFO 配對: 同 (symbol, positionSide) 分組, 開倉入隊, 平倉出隊配對 → round-trip"""
    # 分組
    groups: dict[tuple, list] = {}
    for t in trades:
        info = t.get("info", {})
        pos_side = (info.get("positionSide") or "").upper()  # LONG/SHORT
        if not pos_side:
            continue
        sym = simplify_symbol(info.get("symbol") or t.get("symbol"))
        if not sym:
            continue
        groups.setdefault((sym, pos_side), []).append(t)

    closed = []
    fees_total = 0.0

    for (sym, pos_side), grp in groups.items():
        grp.sort(key=lambda x: x.get("timestamp") or 0)
        # LONG: buy=open, sell=close; SHORT: sell=open, buy=close
        open_side = "buy" if pos_side == "LONG" else "sell"
        queue: list[dict] = []  # FIFO of open fills

        for t in grp:
            side = (t.get("side") or "").lower()
            price = float(t.get("price") or 0)
            amount = float(t.get("amount") or 0)
            fee = float((t.get("fee") or {}).get("cost") or 0)
            fees_total += fee
            ts = int(t.get("timestamp") or 0)

            if side == open_side:
                queue.append({"price": price, "amount": amount, "ts": ts, "fee": fee})
            else:
                # 平倉: FIFO 配對
                remaining = amount
                while remaining > 0.0000001 and queue:
                    entry = queue[0]
                    matched = min(remaining, entry["amount"])
                    # PnL: LONG=(exit-entry)*qty, SHORT=(entry-exit)*qty
                    if pos_side == "LONG":
                        pnl = (price - entry["price"]) * matched
                    else:
                        pnl = (entry["price"] - price) * matched
                    # 按比例分攤手續費
                    entry_fee_share = entry["fee"] * (matched / entry["amount"]) if entry["amount"] > 0 else 0
                    close_fee_share = fee * (matched / amount) if amount > 0 else 0
                    net_pnl = pnl - entry_fee_share - close_fee_share

                    closed.append({
                        "symbol": sym,
                        "side": pos_side,
                        "positionAmt": matched,
                        "avgPrice": entry["price"],
                        "exitPrice": price,
                        "leverage": 0.0,
                        "unrealizedProfit": 0.0,
                        "realizedProfit": round(net_pnl, 4),
                        "pnlRatio": round(net_pnl / (entry["price"] * matched) * 100, 2) if entry["price"] * matched > 0 else 0.0,
                        "positionValue": round(entry["price"] * matched, 2),
                        "liquidationPrice": 0.0,
                        "status": "CLOSED",
                        "ts": ts,
                        "openTs": entry["ts"],
                    })
                    entry["amount"] -= matched
                    entry["fee"] -= entry_fee_share
                    remaining -= matched
                    if entry["amount"] <= 0.0000001:
                        queue.pop(0)

    # 去重
    seen = set()
    deduped = []
    for r in closed:
        fp = (r["symbol"], r["side"], r["avgPrice"], r["exitPrice"], r["ts"], r["realizedProfit"])
        if fp not in seen:
            seen.add(fp)
            deduped.append(r)

    return deduped, fees_total


def build_snapshot() -> dict:
    ex = _client()
    if ex is None:
        logger.error("ccxt client 不可用")
        return {"generated_at": datetime.now(timezone.utc).isoformat(), "source": "bingx", "count": 0, "records": []}

    # 1) 當前持倉
    positions = fetch_positions(ex)
    logger.info("positions: %d", len(positions))

    # 2) 收集所有要查的 symbol (持倉 + 已知)
    symbols = set(KNOWN_SYMBOLS)
    for p in positions:
        # 反推 ccxt symbol (简化版: 加回 /USDT:USDT)
        pass  # KNOWN_SYMBOLS 已涵蓋
    symbols = sorted(symbols)

    # 3) 抓歷史成交
    logger.info("fetching trades for %d symbols...", len(symbols))
    raw_trades = fetch_all_trades(ex, symbols)
    logger.info("total raw trades: %d", len(raw_trades))

    # 4) 配對
    closed, fees = pair_trades(raw_trades)
    logger.info("paired closed: %d, fees: %.4f", len(closed), fees)

    recs = positions + closed
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "bingx-ccxt-trades",
        "repo": REPO,
        "count": len(recs),
        "fees_total": round(fees, 4),
        "records": recs,
    }


def _gh_put(path: str, content: str, message: str) -> tuple[bool, str]:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return False, "GITHUB_TOKEN missing"
    h = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"}
    api = f"https://api.github.com/repos/{REPO}/contents/{path}"
    existing = None
    try:
        with urllib.request.urlopen(urllib.request.Request(api, headers=h), timeout=20) as r:
            existing = json.loads(r.read().decode())
    except Exception:
        pass
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": "master",
    }
    if existing and existing.get("sha"):
        payload["sha"] = existing["sha"]
    req = urllib.request.Request(api, data=json.dumps(payload).encode(), method="PUT", headers=h)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return True, "pushed" if r.status in (200, 201) else str(r.status)
        except Exception as e:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
            else:
                return False, str(e)[:200]
    return False, "unknown"


def persist(snap: dict) -> str:
    if snap.get("count", 0) == 0:
        logger.warning("skip empty snapshot")
        return ""
    os.makedirs(os.path.join(ROOT, TRADES_PREFIX), exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"trades_{ts}.json"
    local = os.path.join(ROOT, TRADES_PREFIX, fname)
    with open(local, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    logger.info("local: %s (%d records)", local, snap["count"])
    ok, detail = _gh_put(f"{TRADES_PREFIX}/{fname}", json.dumps(snap, ensure_ascii=False, indent=2), f"trade bot: {fname}")
    logger.info("github: %s %s", ok, detail)
    return fname


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--interval", type=int, default=300)
    args = ap.parse_args()

    if not os.environ.get("BINGX_API_KEY") or not os.environ.get("BINGX_API_SECRET"):
        logger.error("BINGX_API_KEY / BINGX_API_SECRET 未設置")
        raise SystemExit(1)

    if args.daemon:
        while True:
            try:
                snap = build_snapshot()
                persist(snap)
            except Exception as e:
                logger.exception("loop err: %s", e)
            time.sleep(args.interval)
    else:
        snap = build_snapshot()
        fname = persist(snap)
        print(f"OK {fname} records={snap['count']}")


if __name__ == "__main__":
    main()
