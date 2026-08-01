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
CACHE_TTL = 900  # 15 min (之前 5 min 太短, 快照每4h才更新)


def _gh_get(api_base: str, path: str):
    req = urllib.request.Request(f"{api_base}/{path}", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401 and _token:
            # token 失效 → 拔掉 Authorization 重試 (public repo 無需 auth)
            logger.warning("gh trades get %s -> 401, retrying without token", path)
            headers_noauth = {k: v for k, v in HEADERS.items() if k != "Authorization"}
            req2 = urllib.request.Request(f"{api_base}/{path}", headers=headers_noauth)
            try:
                with urllib.request.urlopen(req2, timeout=20) as r:
                    return json.loads(r.read().decode("utf-8"))
            except Exception as e2:
                logger.warning("gh trades get %s (noauth) -> %s", path, e2)
                return None
        logger.warning("gh trades get %s -> %s", path, e)
        return None
    except Exception as e:
        logger.warning("gh trades get %s -> %s", path, e)
        return None


def _list_files(api_base: str) -> list[str]:
    req = urllib.request.Request(api_base, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [f["name"] for f in data if f["name"].endswith(".json")]
    except urllib.error.HTTPError as e:
        if e.code == 401 and _token:
            logger.warning("gh trades list -> 401, retrying without token")
            headers_noauth = {k: v for k, v in HEADERS.items() if k != "Authorization"}
            req2 = urllib.request.Request(api_base, headers=headers_noauth)
            try:
                with urllib.request.urlopen(req2, timeout=20) as r:
                    data = json.loads(r.read().decode("utf-8"))
                return [f["name"] for f in data if f["name"].endswith(".json")]
            except Exception as e2:
                logger.warning("gh trades list (noauth) -> %s", e2)
                return []
        logger.warning("gh trades list -> %s", e)
        return []
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


def _latest_snapshot_name() -> str | None:
    """找到最新的 trades 快照檔名。

    優先: GitHub commits API (path=trades/) 按時間排序, 無 1000 檔截斷問題。
    Fallback: contents API 字母序最後一個 (有截斷風險)。
    """
    # 1) commits API — 按 commit 時間排序, 拿最近一次動到 trades/ 的 commit
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/commits?path=trades/&per_page=5",
            headers=HEADERS,  # 有 GITHUB_TOKEN 時可拿到 files 明細
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                commits = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401 and _token:
                # token 失效 → 拔掉 Authorization 重試
                logger.warning("commits API -> 401, retrying without token")
                headers_noauth = {k: v for k, v in HEADERS.items() if k != "Authorization"}
                req2 = urllib.request.Request(
                    f"https://api.github.com/repos/{REPO}/commits?path=trades/&per_page=5",
                    headers=headers_noauth,
                )
                with urllib.request.urlopen(req2, timeout=20) as r:
                    commits = json.loads(r.read().decode("utf-8"))
            else:
                raise
        for c in commits:
            files = c.get("files", []) or []
            for f in files:
                fn = f.get("filename", "")
                if fn.startswith("trades/") and fn.endswith(".json"):
                    return fn.split("/", 1)[1]
            # 沒帶 files (未授權時), 從 commit message 猜檔名
            msg = c.get("commit", {}).get("message", "")
            m = _re.search(r"trades_(\d{8}_\d{6})\.json", msg)
            if m:
                return f"trades_{m.group(1)}.json"
    except Exception as e:
        logger.warning("commits API -> %s", e)

    # 2) contents API fallback — 字母序 (predict_history.json 開頭, 最新 trades 在最後)
    try:
        names = sorted(_list_files(TRADES_API))
        if names:
            return names[-1]
    except Exception as e:
        logger.warning("contents fallback -> %s", e)
    return None


def _load_all_trades() -> dict:
    """從多份快照合併所有歷史交易（全量去重）。"""
    now = time.time()
    with _cache_lock:
        if _cache["ts"] and (now - _cache["ts"]) < CACHE_TTL and _cache["records"]:
            return _cache

    latest = _latest_snapshot_name()
    snap = _read_raw(latest) if latest else None
    if not snap:
        return {"records": [], "snapshots": [], "fees_total": None}

    # 從最新快照取得 records
    records = []
    fees_total = 0.0
    funding_total = 0.0
    fees_total_all = 0.0

    def _enrich(rec, snap_name):
        rec["_snapshot"] = snap_name
        rec["symbol"] = norm_sym(rec.get("symbol"))
        rec["qty"] = rec.get("positionAmt")
        rec["notional"] = rec.get("positionValue")
        rec["fee"] = round(float(rec.get("entry_fee") or 0) + float(rec.get("exit_fee") or 0), 6)
        rec["closeTime"] = rec.get("ts")
        open_ts = rec.get("openTs") or 0
        close_ts = rec.get("ts") or 0
        rec["holdDuration"] = (close_ts - open_ts) if open_ts and close_ts and close_ts > open_ts else None

    for rec in snap.get("records", []):
        _enrich(rec, latest)
        records.append(rec)
    fees_total = float(snap.get("fees_total") or 0)
    funding_total = float(snap.get("funding_total") or 0)
    fees_total_all = float(snap.get("fees_total_all") or 0)

    # 建立 fingerprint 集合（用於後續去重）
    seen: set = set()
    for r in records:
        if r.get("status") == "OPEN":
            fp = ("OPEN", r.get("symbol"), r.get("side"), r.get("avgPrice"), r.get("positionAmt"))
        else:
            fp = ("CLOSED", r.get("symbol"), r.get("side"),
                  r.get("open_order_id"), r.get("close_order_id"), r.get("realizedProfit"))
        seen.add(fp)

    # 從舊全量快照補充更多歷史記錄（7/31 全量快照有 2557 筆）
    old_snapshots = [
        "trades_20260731_065042.json",
        "trades_20260731_064643.json",
    ]
    for fn in old_snapshots:
        if fn == latest:
            continue
        old = _read_raw(fn)
        if old:
            for rec in old.get("records", []):
                if rec.get("status") == "CLOSED":
                    fp = ("CLOSED", rec.get("symbol"), rec.get("side"),
                          rec.get("open_order_id"), rec.get("close_order_id"), rec.get("realizedProfit"))
                    if fp not in seen:
                        seen.add(fp)
                        _enrich(rec, fn)
                        records.append(rec)
                elif rec.get("status") == "OPEN":
                    fp = ("OPEN", rec.get("symbol"), rec.get("side"), rec.get("avgPrice"), rec.get("positionAmt"))
                    if fp not in seen:
                        seen.add(fp)
                        _enrich(rec, fn)
                        records.append(rec)

    # 最終排序
    deduped = records
    deduped.sort(key=lambda x: int(x.get("ts") or 0), reverse=True)

    # 費用：從所有合併記錄累計 entry_fee + exit_fee
    fees_total_all = round(sum(
        float(r.get("entry_fee") or 0) + float(r.get("exit_fee") or 0)
        for r in deduped
    ), 4) if deduped else 0.0
    if not fees_total_all:
        fees_total_all = float(os.environ.get("FEE_TOTAL_ALL", "0") or 0)

    result = {
        "ts": now,
        "records": deduped,
        "snapshots": [{"file": latest}],
        "fees_total": round(fees_total, 4),
        "fees_total_all": round(fees_total_all, 4),
        "funding_total": round(funding_total, 4),
        "metrics_30d": snap.get("metrics_30d") if snap else None,
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
    """Fetch Predict.fun trades from GitHub (persisted by bot)."""
    now = time.time()
    if _predict_cache["ts"] and (now - _predict_cache["ts"]) < PREDICT_CACHE_TTL and _predict_cache["data"]:
        return _predict_cache["data"]

    try:
        # Read from GitHub
        data = _gh_get(f"https://api.github.com/repos/{REPO}/contents", "trades/predict_history.json")
        if not data or "content" not in data:
            logger.warning("predict_history.json not found on GitHub")
            return _predict_cache.get("data", [])
        
        import base64
        content = base64.b64decode(data["content"]).decode("utf-8")
        snapshot = json.loads(content)
        records = snapshot.get("records", [])
        
        # Enrich with market details (outcome status)
        token = _predict_auth()
        if token:
            key = os.environ.get("PREDICT_API_KEY", "")
            headers = {"x-api-key": key, "Authorization": f"Bearer {token}"}
            import requests as _req
            
            market_cache = {}
            for rec in records:
                market_id = rec.get("market_id")
                if not market_id or rec.get("status") == "CLOSED":
                    continue
                
                # Fetch market status
                if market_id not in market_cache:
                    try:
                        mr = _req.get(f"{PREDICT_BASE}/markets/{market_id}", headers=headers, timeout=10)
                        market_cache[market_id] = mr.json().get("data", {})
                    except Exception:
                        market_cache[market_id] = {}
                
                market = market_cache[market_id]
                outcomes = market.get("outcomes", [])
                
                # Determine outcome
                for o in outcomes:
                    if o.get("indexSet") == 1:
                        outcome_status = o.get("status", "PENDING")
                        if outcome_status == "WON":
                            rec["status"] = "CLOSED"
                            rec["realizedProfit"] = round(rec.get("bet_usd", 0) * (1.0 / rec.get("ask_price", 1) - 1), 4)
                            rec["exitPrice"] = 1.0
                        elif outcome_status == "LOST":
                            rec["status"] = "CLOSED"
                            rec["realizedProfit"] = -rec.get("bet_usd", 0)
                            rec["exitPrice"] = 0.0
                        break
        
        _predict_cache["ts"] = now
        _predict_cache["data"] = records
        return records
    except Exception as e:
        logger.warning("predict github fetch failed: %s", e)
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
        "funding_total": data.get("funding_total", 0),
        "metrics_30d": data.get("metrics_30d"),
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
