"""
Trades API — 從 GitHub repo 讀取所有歷史交易快照 + Predict.fun 持倉。

資料來源:
  1. BingX: bot/trade_bot.py 每4h抓取 → GitHub trades/ 目錄 (所有快照合併去重)
  2. Predict.fun: /positions API 即時讀取 (15m BTC/ETH 預測市場)
"""
from __future__ import annotations

import os
import json
import time
import logging
import base64
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from fastapi import APIRouter

logger = logging.getLogger(__name__)

import re as _re


def norm_sym(sym):
    if not sym:
        return sym
    s = str(sym).strip().replace(":USDT", "").replace(":USDC", "")
    m = _re.match(r"^NCFX(\w+?)2(\w+)-USDT$", s)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = _re.match(r"^NC(CO|SK|SI)\d*(.+?)2USD-USDT$", s)
    if m:
        return m.group(2)
    m = _re.match(r"^NC(\w+)-USDT$", s)
    if m:
        return m.group(1)
    if s.endswith("-USDT"):
        return s[: -len("-USDT")]
    return s


router = APIRouter(prefix="/api/trades", tags=["trades"])

REPO = "vincepeng518/quant-backtest-platform"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/master"
TRADES_API = f"https://api.github.com/repos/{REPO}/contents/trades"
ARB_TRADES_API = f"https://api.github.com/repos/{REPO}/contents/arb-trades"
HEADERS = {"Accept": "application/vnd.github+json"}
_token = os.environ.get("GITHUB_TOKEN")
if _token:
    HEADERS["Authorization"] = f"Bearer {_token}"

# ── Cache ──
_cache_lock = Lock()
_cache: dict = {"ts": 0, "records": [], "snapshots": [], "fees_total": None}
CACHE_TTL = 300  # 5 min


def _gh_get(api_base: str, path: str):
    req = urllib.request.Request(f"{api_base}/{path}", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        logger.warning("gh trades get %s -> %s", path, e)
        return None


def _list_files(api_base: str) -> list[str]:
    req = urllib.request.Request(api_base, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [f["name"] for f in data if f["name"].endswith(".json")]
    except Exception as e:
        logger.warning("gh trades list -> %s", e)
        return []


def _read_raw(filename: str) -> dict | None:
    """Read a single snapshot file via raw.githubusercontent.com (fast, no auth)."""
    url = f"{RAW_BASE}/trades/{filename}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        logger.warning("raw read %s -> %s", filename, e)
        return None


def _load_all_trades() -> dict:
    """Read ALL snapshot files, merge + dedupe records."""
    now = time.time()
    with _cache_lock:
        if _cache["ts"] and (now - _cache["ts"]) < CACHE_TTL and _cache["records"]:
            return _cache

    names = sorted(_list_files(TRADES_API))
    if not names:
        return {"records": [], "snapshots": [], "fees_total": None}

    # Read all files in parallel (raw.githubusercontent.com, no auth needed)
    all_records: list = []
    fees_total = 0.0
    snapshots = [{"file": n} for n in names]

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_read_raw, n): n for n in names}
        for fut in as_completed(futures):
            snap = fut.result()
            if not snap:
                continue
            for rec in snap.get("records", []):
                rec["_snapshot"] = futures[fut]
                rec["symbol"] = norm_sym(rec.get("symbol"))
                all_records.append(rec)
            fees_total += float(snap.get("fees_total") or 0)

    # Dedupe: OPEN positions by identity (same position in every snapshot),
    # CLOSED by full trade fingerprint
    seen: set = set()
    deduped: list = []
    for r in all_records:
        if r.get("status") == "OPEN":
            fp = ("OPEN", r.get("symbol"), r.get("side"), r.get("avgPrice"), r.get("positionAmt"))
        else:
            fp = ("CLOSED", r.get("symbol"), r.get("side"),
                  r.get("avgPrice"), r.get("exitPrice"),
                  r.get("ts"), r.get("realizedProfit"))
        if fp in seen:
            continue
        seen.add(fp)
        deduped.append(r)

    # Sort by ts descending (newest first)
    deduped.sort(key=lambda x: int(x.get("ts") or 0), reverse=True)

    result = {
        "ts": now,
        "records": deduped,
        "snapshots": snapshots,
        "fees_total": round(fees_total, 4),
    }
    with _cache_lock:
        _cache.update(result)
    return result


# ── Predict.fun ──
PREDICT_BASE = "https://api.predict.fun/v1"
_predict_cache: dict = {"ts": 0, "data": []}
PREDICT_CACHE_TTL = 60  # 1 min


def _predict_auth() -> str | None:
    """Get Predict.fun JWT token."""
    try:
        import requests as _req
        from predict_sdk.order_builder import OrderBuilder  # type: ignore
        from predict_sdk.types import OrderBuilderOptions  # type: ignore
        from eth_account import Account
    except ImportError:
        logger.warning("predict_sdk/requests not installed")
        return None

    key = os.environ.get("PREDICT_API_KEY", "")
    pk = os.environ.get("PREDICT_PRIVATE_KEY", "")
    sw = os.environ.get("PREDICT_SMART_WALLET", "0x06eae10db3e3b813c88F17326B02f4bcaD2f766b")
    if not key or not pk:
        return None

    try:
        acct = Account.from_key(pk)
        opts = OrderBuilderOptions(predict_account=sw)
        builder = OrderBuilder.make(56, signer=acct, options=opts)  # type: ignore

        r = _req.get(f"{PREDICT_BASE}/auth/message", headers={"x-api-key": key}, timeout=10)
        msg = r.json()["data"]["message"]
        sig = builder.sign_predict_account_message(msg)

        r2 = _req.post(f"{PREDICT_BASE}/auth",
            headers={"x-api-key": key, "Content-Type": "application/json"},
            json={"signer": sw, "signature": sig, "message": msg}, timeout=10)
        return r2.json()["data"]["token"]
    except Exception as e:
        logger.warning("predict auth failed: %s", e)
        return None


def _fetch_predict_positions() -> list:
    """Fetch Predict.fun positions (trade history for 15m markets)."""
    now = time.time()
    if _predict_cache["ts"] and (now - _predict_cache["ts"]) < PREDICT_CACHE_TTL and _predict_cache["data"]:
        return _predict_cache["data"]

    token = _predict_auth()
    if not token:
        return _predict_cache.get("data", [])

    key = os.environ.get("PREDICT_API_KEY", "")
    try:
        import requests as _req
        r = _req.get(f"{PREDICT_BASE}/positions",
            headers={"x-api-key": key, "Authorization": f"Bearer {token}"}, timeout=15)
        data = r.json()

        positions = data.get("data", [])
        records = []
        for p in positions:
            market = p.get("market", {})
            outcomes = market.get("outcomes", [])
            # Find the outcome we hold (indexSet=1 = Up/YES)
            outcome_status = "PENDING"
            for o in outcomes:
                if o.get("indexSet") == 1:
                    outcome_status = o.get("status", "PENDING")
                    break

            amount_wei = int(p.get("amount", "0"))
            amount = amount_wei / 1e18
            avg_buy = float(p.get("averageBuyPriceUsd", 0))
            cost = amount * avg_buy

            # Determine P&L based on outcome status
            if outcome_status == "WON":
                pnl = amount * 1.0 - cost  # payout = $1 per share
                status = "CLOSED"
            elif outcome_status == "LOST":
                pnl = -cost
                status = "CLOSED"
            else:
                pnl = 0.0
                status = "OPEN"

            # Extract market info
            slug = market.get("categorySlug", "")
            # e.g. "btc-updown-15m-1784803500" -> BTC 15m
            sym = "BTC" if "btc" in slug.lower() else ("ETH" if "eth" in slug.lower() else slug)
            end_time = market.get("boostEndsAt", "")

            records.append({
                "symbol": f"{sym}-15m",
                "side": "YES",
                "positionAmt": round(amount, 4),
                "avgPrice": avg_buy,
                "exitPrice": 1.0 if outcome_status == "WON" else (0.0 if outcome_status == "LOST" else 0.0),
                "leverage": 1.0,
                "unrealizedProfit": 0.0 if status == "CLOSED" else round(-cost, 4),
                "realizedProfit": round(pnl, 4) if status == "CLOSED" else 0.0,
                "pnlRatio": 0.0,
                "positionValue": round(cost, 4),
                "liquidationPrice": 0.0,
                "status": status,
                "ts": int(time.time() * 1000),
                "market_slug": slug,
                "end_time": end_time,
                "outcome": outcome_status,
                "source": "predict.fun",
            })

        _predict_cache["ts"] = now
        _predict_cache["data"] = records
        return records
    except Exception as e:
        logger.warning("predict positions failed: %s", e)
        return _predict_cache.get("data", [])


# ── Routes ──

@router.get("/arb")
async def get_arb_trades():
    """arb-bot 成交記錄 (GitHub arb-trades/fills.json)."""
    names = _list_files(ARB_TRADES_API)
    records = []
    if names:
        target = "fills.json" if "fills.json" in names else sorted(names)[-1]
        obj = _gh_get(ARB_TRADES_API, target)
        if obj and "content" in obj:
            try:
                snap = json.loads(base64.b64decode(obj["content"]).decode("utf-8"))
                if isinstance(snap, list):
                    records = snap
                elif isinstance(snap, dict):
                    records = snap.get("records", [])
            except Exception:
                pass
    for rec in records:
        rec.setdefault("_snapshot", "arb-trades/fills.json")
    metrics = _calc_metrics(records)
    return {"total": len(records), "snapshots": [{"file": n} for n in sorted(names)],
            "records": records, "metrics": metrics, "fees_total": None, "source": "arb-bot"}


@router.get("/predict")
async def get_predict_trades():
    """Predict.fun 15m BTC/ETH 預測市場交易記錄。"""
    records = _fetch_predict_positions()
    metrics = _calc_metrics(records)
    return {
        "total": len(records),
        "records": records,
        "metrics": metrics,
        "source": "predict.fun",
    }


@router.get("")
async def get_trades():
    """回傳所有 BingX 歷史交易記錄 (合併所有快照去重) + Predict.fun。"""
    data = _load_all_trades()
    records = data["records"]
    metrics = _calc_metrics(records)

    # Also fetch Predict.fun
    predict_records = _fetch_predict_positions()

    return {
        "total": len(records),
        "snapshots": data["snapshots"],
        "records": records,
        "metrics": metrics,
        "fees_total": data["fees_total"],
        "source": "bingx-all-snapshots",
        "predict": {
            "total": len(predict_records),
            "records": predict_records,
            "metrics": _calc_metrics(predict_records),
        },
    }


def _calc_metrics(records: list, periods_per_year: int = 252) -> dict:
    """Sharpe / Sortino / Calmar / Annual Return / Max Drawdown / Profit Factor."""
    try:
        import numpy as np
    except Exception:
        return {}
    pnls = []
    for r in records:
        rp = float(r.get("realizedProfit") or 0)
        up = float(r.get("unrealizedProfit") or 0)
        p = rp + up
        if p != 0:
            pnls.append(p)
    if len(pnls) < 2:
        return {"sharpe": None, "sortino": None, "calmar": None,
                "annual_return": None, "max_drawdown": None,
                "profit_factor": None, "trade_count": len(pnls)}
    arr = np.array(pnls, dtype=float)
    n = len(arr)
    mean = arr.mean()
    std = arr.std(ddof=1)
    sharpe = float((mean / std) * np.sqrt(periods_per_year)) if std > 0 else 0.0
    downside = arr[arr < 0]
    dstd = downside.std(ddof=1) if len(downside) > 1 else 0.0
    if dstd > 0:
        sortino = float((mean / dstd) * np.sqrt(periods_per_year))
    elif mean > 0:
        sortino = None
    else:
        sortino = 0.0
    cum = np.cumsum(arr)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = float(dd.max()) if len(dd) else 0.0
    calmar = float((mean * periods_per_year) / max_dd) if max_dd > 0 else None
    annual_return = float(mean * periods_per_year)
    gains = arr[arr > 0].sum()
    losses = -arr[arr < 0].sum()
    pf = float(gains / losses) if losses > 0 else (float("inf") if gains > 0 else 0.0)
    return {
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3) if sortino is not None else None,
        "calmar": round(calmar, 3) if calmar is not None else None,
        "annual_return": round(annual_return, 2),
        "max_drawdown": round(max_dd, 2),
        "profit_factor": round(pf, 3) if pf != float("inf") else None,
        "trade_count": n,
    }
