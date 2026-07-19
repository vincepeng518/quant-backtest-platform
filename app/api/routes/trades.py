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

# symbol 簡化映射 (與 bot/trade_bot.py 同步)
SYMBOL_MAP = {
    "NCCOGOLD2USD-USDT": "GOLD-USDT",
}


def norm_sym(sym):
    if not sym:
        return sym
    return SYMBOL_MAP.get(sym, sym)


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
    names = _list_files()
    records = []
    snapshots = []
    for n in sorted(names):
        obj = _gh_get(n)
        if not obj or "content" not in obj:
            continue
        import base64
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
        for rec in snap.get("records", []):
            rec["_snapshot"] = n
            rec["symbol"] = norm_sym(rec.get("symbol"))
            records.append(rec)
    # 專業績效指標: 只用最新快照 (避免多 snapshot 重複計算同一持倉)
    latest_recs = []
    if snapshots:
        latest_file = snapshots[-1]["file"]
        latest_recs = [r for r in records if r.get("_snapshot") == latest_file]
    metrics = _calc_metrics(latest_recs if latest_recs else records)
    return {"total": len(records), "snapshots": snapshots, "records": records, "metrics": metrics}


def _calc_metrics(records: list) -> dict:
    """Sharpe / Max Drawdown / Profit Factor (empyrical 風格, 純 numpy)。"""
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
        return {"sharpe": None, "max_drawdown": None, "profit_factor": None, "trade_count": len(pnls)}
    arr = np.array(pnls, dtype=float)
    # Sharpe (年化係數簡化: 用 sqrt(N) 當 proxy, 樣本小不嚴謹)
    mean = arr.mean()
    std = arr.std(ddof=1)
    sharpe = float((mean / std) * np.sqrt(len(arr))) if std > 0 else 0.0
    # Max Drawdown (累積 PnL 峰值回撤)
    cum = np.cumsum(arr)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = float(dd.max()) if len(dd) else 0.0
    # Profit Factor (總盈利 / 總虧損)
    gains = arr[arr > 0].sum()
    losses = -arr[arr < 0].sum()
    pf = float(gains / losses) if losses > 0 else (float("inf") if gains > 0 else 0.0)
    return {
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(max_dd, 2),
        "profit_factor": round(pf, 3) if pf != float("inf") else None,
        "trade_count": len(pnls),
    }
