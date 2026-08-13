"""
Generate trades/latest_trades.json — 跨月最新 50 筆,供交易表格首載。
依 ts 全量降冪取前 N 筆(跨月),資料存 GitHub。
用法: python3 scripts/gen_latest_trades.py (N 預設 50, 可傳參)
"""
from __future__ import annotations
import json
import os
import glob
import datetime
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BY_MONTH_DIR = os.path.join(REPO_ROOT, "trades", "by-month")
OUT_PATH = os.path.join(REPO_ROOT, "trades", "latest_trades.json")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 50


def load_all():
    recs = []
    for p in sorted(glob.glob(os.path.join(BY_MONTH_DIR, "*.json"))):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            recs.extend(d.get("records", []))
        except Exception as e:
            print("skip", p, e)
    return recs


def main():
    records = load_all()
    # ts 降冪(新股在上)
    srt = sorted(records, key=lambda r: int(r.get("ts") or 0), reverse=True)
    latest = srt[:N]
    # 涵蓋月份(降冪)
    months = []
    seen_m = set()
    for r in sorted(latest, key=lambda x: int(x.get("ts") or 0), reverse=True):
        ts = r.get("ts")
        if ts:
            m = datetime.datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m")
            if m not in seen_m:
                seen_m.add(m)
                months.append(m)

    payload = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "count": len(latest),
        "months": months,
        "records": latest,   # 已 ts 降冪
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    kb = os.path.getsize(OUT_PATH) / 1024
    print(f"latest_trades.json: {len(latest)} 筆 / {kb:.1f} KB / 涵蓋月 {months[:4]}...")

    # 印前 3 筆 ts 供驗證排序
    for r in latest[:3]:
        st = datetime.datetime.utcfromtimestamp((r.get('ts') or 0) / 1000)
        print(f"  {st:%Y-%m-%d %H:%M} {r.get('symbol')} {r.get('side')} pnl={r.get('realizedProfit')}")


if __name__ == "__main__":
    main()
