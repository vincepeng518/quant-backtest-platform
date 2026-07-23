"""
Trade Bot — 自動抓取 BingX 交易數據並永久寫入 GitHub。

修正:
- 用 info.volume (合約數) 取代 ccxt amount (有解析錯誤)
- 槓桿 = 名義本金 / 保證金 (info.volume * price / info.amount)
- 價格保持原始精度 (不強制四捨五入)
- 加入 close_time / fee / margin 欄位
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
    """同 orderId 的分批成交先聚合 (加總合約數/保證金, 加權均價)"""
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
            total_vol = 0.0
            total_margin = 0.0
            weighted_price = 0.0
            total_fee = 0.0
            ts = base.get("timestamp", 0)
            for t in grp:
                info = t.get("info", {})
                vol = float(info.get("volume", 0) or 0)
                margin = float(info.get("amount", 0) or 0)
                price = float(t.get("price", 0))
                fee = float((t.get("fee") or {}).get("cost", 0) or 0)
                weighted_price += price * vol
                total_vol += vol
                total_margin += margin
                total_fee += fee
                ts = max(ts, t.get("timestamp", 0))
            avg_price = weighted_price / total_vol if total_vol > 0 else 0
            # 用 info.volume 做 ccxt amount (因 ccxt amount 有解析錯誤)
            # 複製 base 並覆蓋關鍵欄位
            merged = dict(base)
            merged["amount"] = total_vol  # 用 info.volume 總和
            merged["price"] = avg_price
            merged["cost"] = total_vol * avg_price
            merged["fee"] = {"currency": "USDT", "cost": total_fee}
            merged["timestamp"] = ts
            merged["info"] = dict(base.get("info", {}))
            merged["info"]["volume"] = str(total_vol)
            merged["info"]["amount"] = str(total_margin)
            merged["info"]["commission"] = str(-total_fee)
            out.append(merged)
    return out


def pair_trades(trades: list[dict]) -> tuple[list[dict], float]:
    """FIFO 配對: 同 (symbol, positionSide) 分組, 開倉入隊, 平倉出隊配對"""
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

        for t in grp:
            side = (t.get("side") or "").lower()
            # 使用 info.volume 作為合約數 (ccxt amount 有解析錯誤)
            info = t.get("info", {})
            contracts = float(info.get("volume", 0) or 0)
            margin = float(info.get("amount", 0) or 0)  # 保證金
            price = float(t.get("price") or 0)
            fee = float((t.get("fee") or {}).get("cost") or 0)
            fees_total += fee
            ts = int(t.get("timestamp") or 0)
            order_id = str(info.get("orderId") or "")

            # 計算實際槓桿 = 名義本金 / 保證金
            notional = contracts * price
            leverage = round(notional / margin, 1) if margin > 0 else 1.0

            if side == open_side:
                queue.append({
                    "price": price, "contracts": contracts, "margin": margin,
                    "ts": ts, "fee": fee, "order_id": order_id, "leverage": leverage,
                })
            else:
                remaining = contracts
                while remaining > 0.0000001 and queue:
                    entry = queue[0]
                    matched = min(remaining, entry["contracts"])
                    if pos_side == "LONG":
                        pnl = (price - entry["price"]) * matched
                    else:
                        pnl = (entry["price"] - price) * matched
                    entry_fee_share = entry["fee"] * (matched / entry["contracts"]) if entry["contracts"] > 0 else 0
                    close_fee_share = fee * (matched / contracts) if contracts > 0 else 0
                    net_pnl = pnl - entry_fee_share - close_fee_share
                    close_order_id = order_id
                    open_order_id = entry["order_id"]

                    # 合併槓桿 (取開倉與平倉較大者)
                    lev = max(entry["leverage"], leverage)

                    # 手續費明細
                    entry_fee_str = round(entry_fee_share, 4)
                    close_fee_str = round(close_fee_share, 4)

                    closed.append({
                        "symbol": sym,
                        "side": pos_side,
                        "positionAmt": matched,
                        "avgPrice": round(entry["price"], 6),
                        "exitPrice": round(price, 6),
                        "leverage": lev,
                        "unrealizedProfit": 0.0,
                        "realizedProfit": round(net_pnl, 4),
                        "pnlRatio": round(net_pnl / (entry["price"] * matched) * 100, 4) if entry["price"] * matched > 0 else 0.0,
                        "positionValue": round(entry["price"] * matched, 2),
                        "liquidationPrice": 0.0,
                        "status": "CLOSED",
                        "openTs": entry["ts"],
                        "ts": ts,
                        "open_order_id": open_order_id,
                        "close_order_id": close_order_id,
                        "entry_fee": entry_fee_str,
                        "exit_fee": close_fee_str,
                        "margin": round(entry["margin"] * (matched / entry["contracts"]) if entry["contracts"] > 0 else 0, 4),
                    })
                    entry["contracts"] -= matched
                    entry["fee"] -= entry_fee_share
                    entry["margin"] *= (entry["contracts"] / (entry["contracts"] + matched)) if (entry["contracts"] + matched) > 0 else 0
                    remaining -= matched
                    if entry["contracts"] <= 0.0000001:
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

    symbols = sorted(KNOWN_SYMBOLS)
    logger.info("fetching trades for %d symbols...", len(symbols))
    raw_trades = fetch_all_trades(ex, symbols)
    logger.info("total raw trades: %d", len(raw_trades))

    # 先聚合分批成交, 再配對
    aggregated = aggregate_fills(raw_trades)
    logger.info("after aggregation: %d", len(aggregated))

    closed, fees = pair_trades(aggregated)
    logger.info("paired closed: %d, fees: %.4f", len(closed), fees)

    recs = positions + closed
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "bingx-ccxt-trades-v2",
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