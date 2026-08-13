"""
Generate per-month trade JSON files: trades/by-month/YYYY-MM.json
===============================================================
來源:複刻後端 `_load_all_trades` 合併邏輯:
  - 最新快照(含最近 OPEN + 新平倉)
  - + 2 個全量舊快照(歷史全量)
  按 records `ts` 切分到對應月份,套用後端同款 `_enrich` 欄位。

輸出: trades/by-month/YYYY-MM.json
用法: python3 scripts/gen_monthly_trades.py   (產生後 commit+push)
"""
from __future__ import annotations
import json
import os
import re as _re
import collections
import datetime
import glob

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "trades", "by-month")
TRADES_DIR = os.path.join(REPO_ROOT, "trades")

# 全量舊快照(歷史全量,補充早期交易)
FULL_SNAPSHOTS = [
    "trades_20260731_065042.json",
    "trades_20260728_062541.json",
]


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
        return s[: -5]
    return s


def enrich(rec, snap_name):
    rec["_snapshot"] = snap_name
    rec["symbol"] = norm_sym(rec.get("symbol"))
    rec["qty"] = rec.get("positionAmt")
    rec["notional"] = rec.get("positionValue")
    rec["fee"] = round(float(rec.get("entry_fee") or 0) + float(rec.get("exit_fee") or 0), 6)
    rec["closeTime"] = rec.get("ts")
    open_ts = rec.get("openTs") or 0
    close_ts = rec.get("ts") or 0
    rec["holdDuration"] = (close_ts - open_ts) if open_ts and close_ts and close_ts > open_ts else None
    return rec


def _fingerprint(r):
    if r.get("status") == "OPEN":
        return ("OPEN", r.get("symbol"), r.get("side"), r.get("avgPrice"), r.get("positionAmt"))
    return ("CLOSED", r.get("symbol"), r.get("side"), r.get("open_order_id"),
            r.get("close_order_id"), r.get("realizedProfit"))


def latest_snapshot_name():
    """最新快照 = 最新的 trades_*.json(mtime)。"""
    cands = [f for f in glob.glob(os.path.join(TRADES_DIR, "trades_*.json"))
             if "by-month" not in f]
    if not cands:
        return None
    cands.sort(key=os.path.getmtime, reverse=True)
    return os.path.basename(cands[0])


def main():
    latest = latest_snapshot_name()
    if not latest:
        print("找不到任何 trades 快照"); return

    seen = set()
    records = []

    # 1) 最新快照(主)
    with open(os.path.join(TRADES_DIR, latest), "r", encoding="utf-8") as f:
        snap = json.load(f)
    for r in snap.get("records", []):
        fp = _fingerprint(r)
        if fp in seen:
            continue
        seen.add(fp)
        records.append(enrich(r, latest))

    # 2) 全量舊快照補歷史
    for fn in FULL_SNAPSHOTS:
        p = os.path.join(TRADES_DIR, fn)
        if fn == latest or not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as f:
            old = json.load(f)
        for r in old.get("records", []):
            fp = _fingerprint(r)
            if fp in seen:
                continue
            seen.add(fp)
            records.append(enrich(r, fn))

    # 切分月份
    by_month = collections.OrderedDict()
    for r in records:
        ts = r.get("ts")
        if not ts:
            continue
        m = datetime.datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m")
        by_month.setdefault(m, []).append(r)
    for m in by_month:
        by_month[m].sort(key=lambda x: int(x.get("ts") or 0), reverse=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    report = []
    for m in sorted(by_month):
        recs = by_month[m]
        payload = {"month": m, "source": "github-trades/by-month",
                   "generated_from": latest, "count": len(recs), "records": recs}
        path = os.path.join(OUT_DIR, f"{m}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        report.append((m, len(recs), os.path.getsize(path) / 1024))

    print(f"[來源: {latest}] 已生成月份檔(共 {len(report)} 個月):")
    for m, n, kb in report:
        print(f"  {m}: {n} 筆, {kb:.0f} KB")


if __name__ == "__main__":
    main()
