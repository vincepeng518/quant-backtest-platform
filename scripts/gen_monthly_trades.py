"""
Generate per-month trade JSON files: trades/by-month/YYYY-MM.json
===============================================================
來源:後端 `_load_all_trades` 合併後的權威快照(全量去重)。
做法:按 records 的 `ts` 切分到對應月份,並套用後端 `_enrich` 同款欄位
      (symbol 簡化 / qty / notional / fee / closeTime / holdDuration)。

輸出:寫入 trades/by-month/YYYY-MM.json,每檔含該月 records。
      commit 由外部處理(push 前請先 git add)。

用法: python3 scripts/gen_monthly_trades.py
"""
from __future__ import annotations
import json
import os
import re as _re
import collections
import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = os.path.join(REPO_ROOT, "trades", "trades_20260731_065042.json")
OUT_DIR = os.path.join(REPO_ROOT, "trades", "by-month")


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


def main():
    with open(SNAPSHOT, "r", encoding="utf-8") as f:
        snap = json.load(f)
    raw_records = snap.get("records", [])

    # 去重(與後端同款 fingerprint)
    seen = set()
    records = []
    for r in raw_records:
        if r.get("status") == "OPEN":
            fp = ("OPEN", r.get("symbol"), r.get("side"), r.get("avgPrice"), r.get("positionAmt"))
        else:
            fp = ("CLOSED", r.get("symbol"), r.get("side"), r.get("open_order_id"),
                  r.get("close_order_id"), r.get("realizedProfit"))
        if fp in seen:
            continue
        seen.add(fp)
        records.append(enrich(r, os.path.basename(SNAPSHOT)))

    # 切分月份
    by_month = collections.OrderedDict()
    for r in records:
        ts = r.get("ts")
        if not ts:
            continue
        m = datetime.datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m")
        by_month.setdefault(m, []).append(r)

    # 排序(新股在上,與後端一致 ts desc)
    for m in by_month:
        by_month[m].sort(key=lambda x: int(x.get("ts") or 0), reverse=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    report = []
    for m in sorted(by_month):
        recs = by_month[m]
        payload = {
            "month": m,
            "source": "github-trades/by-month",
            "generated_from": os.path.basename(SNAPSHOT),
            "count": len(recs),
            "records": recs,
        }
        path = os.path.join(OUT_DIR, f"{m}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        kb = os.path.getsize(path) / 1024
        report.append((m, len(recs), kb))

    print("已生成月份檔:")
    for m, n, kb in report:
        print(f"  {m}: {n} 筆, {kb:.0f} KB")
    print(f"共 {len(report)} 個月份檔, 寫入 {OUT_DIR}")


if __name__ == "__main__":
    main()
