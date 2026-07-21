"""
Trades API — 從 GitHub repo 的 trades/ 目錄讀取交易快照 (永久儲存)。

資料由 bot/trade_bot.py 自動抓取 BingX 並寫入 GitHub，本路由負責匯總展示。
"""
from __future__ import annotations

import os
import json
import logging
import urllib.request
import urllib.error

from fastapi import APIRouter

logger = logging.getLogger(__name__)

# symbol 簡化 (與 bot/trade_bot.py simplify_symbol 同步, 用戶規則)
import re as _re


def norm_sym(sym):
    if not sym:
        return sym
    s = str(sym).strip().replace(":USDT", "").replace(":USDC", "")
    # 外匯: NCFX<BASE>2<QUOTE>-USDT → BASE/QUOTE
    m = _re.match(r"^NCFX(\w+?)2(\w+)-USDT$", s)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    # 商品/股票/股指: NC{CO|SK|SI}[數字]<NAME>2USD-USDT → NAME (前導數字如 1OILWTI 去掉)
    m = _re.match(r"^NC(CO|SK|SI)\d*(.+?)2USD-USDT$", s)
    if m:
        return m.group(2)
    # TradFi 變體: NC<NAME>-USDT → NAME (無 2USD 後綴, 例 NCOILWTI-USDT → OILWTI)
    m = _re.match(r"^NC(\w+)-USDT$", s)
    if m:
        return m.group(1)
    # Crypto: 去尾部 -USDT
    if s.endswith("-USDT"):
        return s[: -len("-USDT")]
    return s


router = APIRouter(prefix="/api/trades", tags=["trades"])

REPO = "vincepeng518/quant-backtest-platform"
TRADES_API = f"https://api.github.com/repos/{REPO}/contents/trades"
ARB_TRADES_API = f"https://api.github.com/repos/{REPO}/contents/arb-trades"
HEADERS = {"Accept": "application/vnd.github+json"}
_token = os.environ.get("GITHUB_TOKEN")
if _token:
    HEADERS["Authorization"] = f"Bearer {_token}"


def _gh_get(api_base: str, path: str):
    req = urllib.request.Request(f"{api_base}/{path}", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa
        logger.warning("gh trades get %s -> %s", path, e)
        return None


def _list_files(api_base: str) -> list[str]:
    req = urllib.request.Request(api_base, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [f["name"] for f in data if f["name"].endswith(".json")]
    except Exception as e:  # noqa
        logger.warning("gh trades list -> %s", e)
        return []


@router.get("/arb")
async def get_arb_trades():
    """arb-bot 成交記錄 (GitHub arb-trades/fills.json)."""
    import base64
    names = _list_files(ARB_TRADES_API)
    records = []
    if names:
        # fills.json 是合併檔, 取它
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
    # 標註來源 + 簡化 (arb 用 BTC-5m 固定 symbol, 不需 norm)
    for rec in records:
        rec.setdefault("_snapshot", "arb-trades/fills.json")
    metrics = _calc_metrics(records)
    return {"total": len(records), "snapshots": [{"file": n} for n in sorted(names)],
            "records": records, "metrics": metrics, "fees_total": None, "source": "arb-bot"}


@router.get("")
async def get_trades():
    """回傳所有交易記錄 (扁平化) + 來源快照列表。"""
    import base64
    names = _list_files(TRADES_API)
    # snapshots: 只列檔名
    snapshots = [{"file": n} for n in sorted(names)]
    records = []
    fees_total = None
    # 只取最新快照一次 (避免重複下載同一檔)
    if snapshots:
        latest_file = snapshots[-1]["file"]
        latest_obj = _gh_get(TRADES_API, latest_file)
        if latest_obj and "content" in latest_obj:
            try:
                latest_snap = json.loads(base64.b64decode(latest_obj["content"]).decode("utf-8"))
                for rec in latest_snap.get("records", []):
                    rec["_snapshot"] = latest_file
                    rec["symbol"] = norm_sym(rec.get("symbol"))
                    records.append(rec)
                fees_total = latest_snap.get("fees_total")
            except Exception:
                pass
    metrics = _calc_metrics(records)
    return {"total": len(records), "snapshots": snapshots, "records": records, "metrics": metrics, "fees_total": fees_total}


def _calc_metrics(records: list, periods_per_year: int = 252) -> dict:
    """Sharpe / Sortino / Calmar / Annual Return / Max Drawdown / Profit Factor.

    periods_per_year: 年化因子 (日級=252, 小時級=24*365, 30m=2*24*365). 預設 252 避免高頻 Sharpe 膨脹.
    """
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
    # 正確年化 Sharpe: mean/std * sqrt(periods_per_year)
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
