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


def _trade_key(r):
    """去重鍵。帶 order id 的舊格式用 id(同一秒可能有多筆部分成交);
    2026-08-03 起 bot 不再寫 order id → 用 (symbol, side, 平倉 ts)。
    同一筆在不同快照 realizedProfit/positionAmt 會有尾數差,不能拿來當鍵。"""
    sym = norm_sym(r.get("symbol"))
    if r.get("status") == "OPEN":
        return ("OPEN", sym, r.get("side"), r.get("avgPrice"))
    if r.get("open_order_id") or r.get("close_order_id"):
        # 舊格式同一組 order id 會對應多筆部分成交 → 需帶 realizedProfit 區分
        return ("ID", sym, r.get("side"), r.get("open_order_id"), r.get("close_order_id"), r.get("realizedProfit"))
    return ("TS", sym, r.get("side"), r.get("ts"))


def _snapshot_files():
    """所有 bot 快照,依檔名時間排序(舊→新)。排除已知污染檔 trades_20261231_*。"""
    out = []
    for f in glob.glob(os.path.join(TRADES_DIR, "trades_*.json")):
        b = os.path.basename(f)
        if not _re.match(r"^trades_\d{8}_\d{6}\.json$", b) or b.startswith("trades_20261231"):
            continue
        out.append(b)
    return sorted(out)


def latest_snapshot_name():
    """最新快照 = 檔名時間最新的 trades_*.json(不用 mtime:git checkout 會打亂 mtime)。"""
    files = _snapshot_files()
    return files[-1] if files else None


def main():
    latest = latest_snapshot_name()
    if not latest:
        print("找不到任何 trades 快照"); return

    # 1) 全量舊快照(帶 order id)當歷史底
    closed: dict = {}
    id_era_ts = set()
    for fn in FULL_SNAPSHOTS:
        p = os.path.join(TRADES_DIR, fn)
        if not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as f:
            old = json.load(f)
        for r in old.get("records", []):
            if r.get("status") == "OPEN" or not r.get("ts"):
                continue
            closed.setdefault(_trade_key(r), enrich(r, fn))
            id_era_ts.add((norm_sym(r.get("symbol")), r.get("side"), r.get("ts")))

    # 2) 之後每一份快照都併進來(快照是滾動視窗,只讀最新一份會漏掉中間的平倉)
    start = FULL_SNAPSHOTS[0]
    snaps = [s for s in _snapshot_files() if s >= start]
    for fn in snaps:
        try:
            with open(os.path.join(TRADES_DIR, fn), "r", encoding="utf-8") as f:
                snap = json.load(f)
        except Exception as e:
            print("skip", fn, e)
            continue
        for r in (snap.get("records", []) if isinstance(snap, dict) else snap):
            if r.get("status") == "OPEN" or not r.get("ts"):
                continue
            k = _trade_key(r)
            if (k[1], k[2], r.get("ts")) in id_era_ts:
                continue  # 已在全量歷史快照裡(後期快照會把同一筆拆成不同部分成交數量,不能再算一次)
            closed[k] = enrich(r, fn)  # 後出現的覆蓋(以最新快照的數值為準)

    # 3) OPEN 持倉只取最新快照
    records = list(closed.values())
    with open(os.path.join(TRADES_DIR, latest), "r", encoding="utf-8") as f:
        snap = json.load(f)
    for r in snap.get("records", []):
        if r.get("status") == "OPEN":
            records.append(enrich(r, latest))
    print(f"合併 {len(snaps)} 份快照 → {len(closed)} 筆平倉 + {len(records) - len(closed)} 筆持倉")

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
