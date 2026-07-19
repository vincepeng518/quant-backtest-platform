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
    s = str(sym).strip().replace("/", "-").replace(":USDT", "").replace(":USDC", "")
    # 外匯: NCFX<BASE>2<QUOTE>-USDT → BASE/QUOTE
    m = _re.match(r"^NCFX(\w+?)2(\w+)-USDT$", s)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    # 商品/股票/股指: NC{CO|SK|SI}<NAME>2USD-USDT → NAME
    m = _re.match(r"^NC(CO|SK|SI)(.+?)2USD-USDT$", s)
    if m:
        return m.group(2)
    # Crypto: 去尾部 -USDT
    if s.endswith("-USDT"):
        return s[: -len("-USDT")]
    return s


router = APIRouter(prefix="/api/trades", tags=["trades"])

REPO = "vincepeng518/quant-backtest-platform"
TRADES_API = f"https://api.github.com/repos/{REPO}/contents/trades"
HEADERS = {"Accept": "application/vnd.github+json"}
_token = os.environ.get("GITHUB_TOKEN")
if _token:
    HEADERS["Authorization"] = f"Bearer {_token}"


def _gh_get(path: str):
    req = urllib.request.Request(f"{TRADES_API}/{path}", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa
        logger.warning("gh trades get %s -> %s", path, e)
        return None


def _list_files() -> list[str]:
    req = urllib.request.Request(TRADES_API, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [f["name"] for f in data if f["name"].endswith(".json")]
    except Exception as e:  # noqa
        logger.warning("gh trades list -> %s", e)
        return []


@router.get("")
async def get_trades():
    """回傳所有交易記錄 (扁平化) + 來源快照列表。"""
    import base64
    names = _list_files()
    records = []
    snapshots = []
    for n in sorted(names):
        obj = _gh_get(n)
        if not obj or "content" not in obj:
            continue
        try:
            content = base64.b64decode(obj["content"]).decode("utf-8")
            snap = json.loads(content)
        except Exception:
            continue
        snapshots.append({
            "file": n,
            "generated_at": snap.get("generated_at"),
            "count": snap.get("count"),
        })
    # 只取最新快照的 records (當前持倉狀態, 不攤平歷史 snapshot 避免重複/舊單)
    records = []
    if snapshots:
        latest_file = snapshots[-1]["file"]
        latest_obj = _gh_get(latest_file)
        if latest_obj and "content" in latest_obj:
            try:
                latest_snap = json.loads(base64.b64decode(latest_obj["content"]).decode("utf-8"))
                for rec in latest_snap.get("records", []):
                    rec["_snapshot"] = latest_file
                    rec["symbol"] = norm_sym(rec.get("symbol"))
                    records.append(rec)
            except Exception:
                pass
    metrics = _calc_metrics(records)
    return {"total": len(records), "snapshots": snapshots, "records": records, "metrics": metrics}


def _calc_metrics(records: list) -> dict:
    """Sharpe / Sortino / Calmar / Annual Return / Max Drawdown / Profit Factor
    (empyrical 風格, 純 numpy 自實現, 不依賴外部 lib)。"""
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
    # Sharpe (簡化年化: sqrt(N) 當 proxy)
    sharpe = float((mean / std) * np.sqrt(n)) if std > 0 else 0.0
    # Sortino: 只用下行波動 (負收益 std)
    downside = arr[arr < 0]
    dstd = downside.std(ddof=1) if len(downside) > 1 else 0.0
    if dstd > 0:
        sortino = float((mean / dstd) * np.sqrt(n))
    elif mean > 0:
        sortino = None  # 無下行風險且盈利 -> 無限大, 顯示 None
    else:
        sortino = 0.0
    # Max Drawdown (累積 PnL 峰值回撤)
    cum = np.cumsum(arr)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = float(dd.max()) if len(dd) else 0.0
    # Calmar = 年化報酬 / 最大回撤 (這裡用 mean*N 當年化 proxy)
    calmar = float((mean * n) / max_dd) if max_dd > 0 else None
    # Annual Return (簡化: mean * N 當年化累積 proxy)
    annual_return = float(mean * n)
    # Profit Factor (總盈利 / 總虧損)
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
