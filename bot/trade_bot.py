"""
Trade Bot — 自動抓取 BingX 交易數據並永久寫入 GitHub。

修正 v3:
- actual_qty = info.amount / price (info.amount 是名義價值 USDT, 非保證金)
- info.volume 是合約張數, 不可直接用
- PnL = (exit - entry) * actual_qty
- 槓桿從 positions 帶入 (歷史單無法取得則標記 null)
- 價格保持原始精度
- 同 orderId 分批成交先聚合再配對
"""

from __future__ import annotations
import os, sys, time, json, argparse, logging, base64, urllib.request
from datetime import datetime, timezone
from collections import defaultdict

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

KNOWN_SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XMR/USDT:USDT",
    "BCH/USDT:USDT", "LDO/USDT:USDT", "JTO/USDT:USDT", "VIRTUAL/USDT:USDT",
    "LONGXIA/USDT:USDT",
    "NCCOGOLD2USD/USDT:USDT", "NCSINASDAQ1002USD/USDT:USDT",
    "NCFXEUR2USD/USDT:USDT", "NCFXGBP2USD/USDT:USDT",
    "NCCO1OILWTI2USD/USDT:USDT",
]


def simplify_symbol(raw: str | None) -> str | None:
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
    """逐 symbol 抓 fetchMyTrades"""
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
                pass
            else:
                logger.warning("  %s: %s", sym, err[:100])
            continue
        time.sleep(0.3)
    return all_trades


def aggregate_fills(trades: list[dict]) -> list[dict]:
    """同 orderId 的分批成交先聚合 (加總名義/數量, 加權均價)
    
    關鍵: info.amount = 名義價值 (USDT), info.volume = 合約張數 (不可直接用)
    actual_qty = info.amount / price
    """
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        order_id = str(t.get("info", {}).get("orderId", ""))
        groups[order_id].append(t)

    out = []
    for order_id, grp in groups.items():
        if len(grp) == 1:
            out.append(grp[0])
        else:
            base = grp[0]
            total_notional = 0.0  # sum of info.amount (USDT)
            total_qty = 0.0       # sum of actual coin qty
            total_fee = 0.0
            ts = base.get("timestamp", 0)
            for t in grp:
                info = t.get("info", {})
                notional = float(info.get("amount", 0) or 0)
                price = float(t.get("price", 0))
                qty = notional / price if price > 0 else 0
                fee = float((t.get("fee") or {}).get("cost", 0) or 0)
                total_notional += notional
                total_qty += qty
                total_fee += fee
                ts = max(ts, t.get("timestamp", 0))
            avg_price = total_notional / total_qty if total_qty > 0 else 0
            merged = dict(base)
            merged["amount"] = total_qty
            merged["price"] = avg_price
            merged["cost"] = total_notional
            merged["fee"] = {"currency": "USDT", "cost": total_fee}
            merged["timestamp"] = ts
            merged["info"] = dict(base.get("info", {}))
            merged["info"]["amount"] = str(total_notional)
            merged["info"]["commission"] = str(-total_fee)
            out.append(merged)
    return out


def pair_trades(trades: list[dict], leverage_map: dict | None = None) -> tuple[list[dict], float]:
    """FIFO 配對: 同 (symbol, positionSide) 分組, 開倉入隊, 平倉出隊配對
    
    關鍵公式:
    - actual_qty = info.amount / price  (info.amount = 名義價值 USDT)
    - PnL = (exit - entry) * actual_qty
    - leverage 從 positions 帶入 (leverage_map), 歷史單無法取得則 null
    """
    leverage_map = leverage_map or {}
    groups: dict[tuple, list] = {}
    for t in trades:
        info = t.get("info", {})
        pos_side = (info.get("positionSide") or "").upper()
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
        open_side = "buy" if pos_side == "LONG" else "sell"
        queue: list[dict] = []
        lev = leverage_map.get(sym)  # 從 positions 帶入的槓桿

        for t in grp:
            side = (t.get("side") or "").lower()
            info = t.get("info", {})
            notional = float(info.get("amount", 0) or 0)  # 名義價值 USDT
            price = float(t.get("price") or 0)
            qty = notional / price if price > 0 else 0     # 實際幣數
            fee = float((t.get("fee") or {}).get("cost") or 0)
            fees_total += fee
            ts = int(t.get("timestamp") or 0)
            order_id = str(info.get("orderId") or "")

            if side == open_side:
                queue.append({
                    "price": price, "qty": qty, "notional": notional,
                    "ts": ts, "fee": fee, "order_id": order_id,
                })
            else:
                remaining = qty
                while remaining > 1e-10 and queue:
                    entry = queue[0]
                    matched = min(remaining, entry["qty"])
                    if pos_side == "LONG":
                        pnl = (price - entry["price"]) * matched
                    else:
                        pnl = (entry["price"] - price) * matched
                    entry_fee_share = entry["fee"] * (matched / entry["qty"]) if entry["qty"] > 0 else 0
                    close_fee_share = fee * (matched / qty) if qty > 0 else 0
                    net_pnl = pnl - entry_fee_share - close_fee_share
                    entry_notional_share = entry["notional"] * (matched / entry["qty"]) if entry["qty"] > 0 else 0

                    closed.append({
                        "symbol": sym,
                        "side": pos_side,
                        "positionAmt": round(matched, 8),
                        "avgPrice": round(entry["price"], 8),
                        "exitPrice": round(price, 8),
                        "leverage": lev,  # 從 positions 帶入, 歷史單可能為 null
                        "unrealizedProfit": 0.0,
                        "realizedProfit": round(net_pnl, 4),
                        "pnlRatio": round(net_pnl / entry_notional_share * 100, 4) if entry_notional_share > 0 else 0.0,
                        "positionValue": round(entry_notional_share, 2),
                        "liquidationPrice": 0.0,
                        "status": "CLOSED",
                        "openTs": entry["ts"],
                        "ts": ts,
                        "open_order_id": entry["order_id"],
                        "close_order_id": order_id,
                        "entry_fee": round(entry_fee_share, 6),
                        "exit_fee": round(close_fee_share, 6),
                        "margin": round(entry_notional_share / lev, 4) if lev and lev > 0 else None,
                    })
                    entry["qty"] -= matched
                    entry["fee"] -= entry_fee_share
                    entry["notional"] -= entry_notional_share
                    remaining -= matched
                    if entry["qty"] <= 1e-10:
                        queue.pop(0)

    # 去重 (order_id fingerprint)
    seen = set()
    deduped = []
    for r in closed:
        fp = (r["symbol"], r["side"], r["open_order_id"], r["close_order_id"], r["realizedProfit"])
        if fp not in seen:
            seen.add(fp)
            deduped.append(r)

    return deduped, fees_total


def build_snapshot() -> dict:
    ex = _client()
    if ex is None:
        logger.error("ccxt client 不可用")
        return {"generated_at": datetime.now(timezone.utc).isoformat(), "source": "bingx", "count": 0, "records": []}

    positions = fetch_positions(ex)
    logger.info("positions: %d", len(positions))

    # 從 positions 建立 leverage_map (symbol → leverage)
    leverage_map = {}
    for p in positions:
        sym = p.get("symbol")
        lev = p.get("leverage")
        if sym and lev and lev > 0:
            leverage_map[sym] = lev
    logger.info("leverage_map: %s", leverage_map)

    symbols = sorted(KNOWN_SYMBOLS)
    logger.info("fetching trades for %d symbols...", len(symbols))
    raw_trades = fetch_all_trades(ex, symbols)
    logger.info("total raw trades: %d", len(raw_trades))

    # 先聚合分批成交, 再配對
    aggregated = aggregate_fills(raw_trades)
    logger.info("after aggregation: %d", len(aggregated))

    closed, fees = pair_trades(aggregated, leverage_map)
    logger.info("paired closed: %d, fees: %.4f", len(closed), fees)

    recs = positions + closed
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "bingx-ccxt-trades-v3",
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