"""
Auxiliary: build trades/summary.json — 全量統計摘要,供 /trades 頁解耦後使用。

攜帶全量統計(Sharpe/PF/多空/勝率/熱圖12週/各月聚合),前端不再需要打 /api/trades 全量。
資料儲存於 GitHub。用法: 在 gen_monthly_trades.py 產完 by-month 後跑本檔,或一併。
   python3 scripts/gen_monthly_trades.py && python3 scripts/gen_trades_summary.py
"""
from __future__ import annotations
import json
import os
import collections
import datetime
import glob
import math

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_DIR = os.path.join(REPO_ROOT, "trades")
BY_MONTH_DIR = os.path.join(TRADES_DIR, "by-month")
OUT_PATH = os.path.join(TRADES_DIR, "summary.json")

# 從已生成的 by-month 檔重建全量(避免重跑合併去重)
def load_all_from_bymonth():
    recs = []
    for p in sorted(glob.glob(os.path.join(BY_MONTH_DIR, "*.json"))):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            recs.extend(d.get("records", []))
        except Exception as e:
            print("skip", p, e)
    return recs


def month_of_ts(ts):
    if not ts:
        return None
    return datetime.datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m")


def date_key_of_ts(ts):
    if not ts:
        return None
    return datetime.datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")


def sort_ts(r):
    return int(r.get("ts") or 0)


def calc_metrics(pnls):
    """複刻後端 _calc_metrics: sharpe/sortino/profit_factor。pnl 非零列表。純 stdlib。"""
    if len(pnls) < 2:
        return {"sharpe": None, "sortino": None, "profit_factor": None}
    n = len(pnls)
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    sharpe = float((mean / std) * math.sqrt(252)) if std > 0 else 0.0
    downside = [x for x in pnls if x < 0]
    if len(downside) > 1:
        dmean = sum(downside) / len(downside)
        dvar = sum((x - dmean) ** 2 for x in downside) / (len(downside) - 1)
        dstd = math.sqrt(dvar) if dvar > 0 else 0.0
    else:
        dstd = 0.0
    sortino = float((mean / dstd) * math.sqrt(252)) if dstd > 0 else (None if mean > 0 else 0.0)
    gains = sum(x for x in pnls if x > 0)
    losses = -sum(x for x in pnls if x < 0)
    pf = float(gains / losses) if losses > 0 else (float("inf") if gains > 0 else 0.0)
    return {
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3) if sortino is not None else None,
        "profit_factor": round(pf, 3) if pf != float("inf") else None,
    }


def main():
    records = load_all_from_bymonth()
    print(f"從 by-month 載入全量: {len(records)} 筆")

    # ---- 全量統計(與交易頁 stats 同邏輯)----
    totalPnl = totalPos = wins = losses = scr = 0
    longPnl = shortPnl = 0
    gainsAmt = lossesAmt = 0
    streak = maxWin = maxLoss = 0
    monthly = collections.OrderedDict()
    dayPnl = collections.defaultdict(float)
    dayCount = collections.defaultdict(int)

    def pnl(r):
        return float(r.get("realizedProfit") or 0) + float(r.get("unrealizedProfit") or 0)

    # 依 ts 排序算連勝
    srt = sorted(records, key=sort_ts)
    for r in srt:
        p = pnl(r)
        totalPnl += p
        totalPos += float(r.get("positionValue") or 0)
        if p > 0:
            wins += 1; gainsAmt += p; streak = streak + 1 if streak > 0 else 1; maxWin = max(maxWin, streak)
        elif p < 0:
            losses += 1; lossesAmt += p; streak = streak - 1 if streak < 0 else -1; maxLoss = max(maxLoss, -streak)
        else:
            scr += 1
        s = str(r.get("side") or "").upper()
        if "LONG" in s: longPnl += p
        elif "SHORT" in s: shortPnl += p
        m = month_of_ts(r.get("ts"))
        k = date_key_of_ts(r.get("ts"))
        if m:
            if m not in monthly: monthly[m] = {"records": 0, "pnl": 0.0, "wins": 0, "losses": 0}
            monthly[m]["records"] += 1
            monthly[m]["pnl"] += p
            if p > 0: monthly[m]["wins"] += 1
            elif p < 0: monthly[m]["losses"] += 1
        if k:
            dayPnl[k] += p
            dayCount[k] += 1

    closed = wins + losses
    winRate = (wins / closed) * 100 if closed > 0 else 0
    avgPnl = totalPnl / closed if closed > 0 else 0

    # 手續費全量
    fees_total_all = round(sum(float(r.get("entry_fee") or 0) + float(r.get("exit_fee") or 0) for r in records), 4) if records else 0

    # 各月聚合 → 降冪月列表
    months_desc = sorted(monthly.keys(), reverse=True)
    monthly_agg = {m: {"records": v["records"], "pnl": round(v["pnl"], 4),
                       "wins": v["wins"], "losses": v["losses"]} for m, v in monthly.items()}

    # 熱圖 12 週(近84天,與交易頁 heatmap 同邏輯)
    today = datetime.date.today()
    heatmap_12w = []
    for i in range(83, -1, -1):
        d = today - datetime.timedelta(days=i)
        key = d.strftime("%Y-%m-%d")
        heatmap_12w.append({"key": key, "pnl": round(dayPnl.get(key, 0.0), 4), "dow": d.weekday()})

    # 12 週熱圖的每日 pnl 是否涵蓋:注意 records 只到 2026-08,heatmap 往前 84 天會到 5月,
    # dayPnl 已有。OK。

    # metrics(sharpe etc) — 用非零 pnl
    pnls = [pnl(r) for r in records if pnl(r) != 0]
    metrics = calc_metrics(pnls)
    trade_count = len(pnls)

    summary = {
        "generated_from": "by-month aggregation",
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "total_records": len(records),
        "months": months_desc,
        "totals": {
            "pnl": round(totalPnl, 4), "position_value": round(totalPos, 4),
            "wins": wins, "losses": losses, "scratch": scr, "win_rate": round(winRate, 2),
            "avg_pnl": round(avgPnl, 4), "long_pnl": round(longPnl, 4), "short_pnl": round(shortPnl, 4),
            "gains_amt": round(gainsAmt, 4), "losses_amt": round(lossesAmt, 4),
            "max_win_streak": maxWin, "max_loss_streak": maxLoss,
            "fees_total": round(fees_total_all, 4),
        },
        "metrics": metrics,
        "trade_count": trade_count,
        "monthly_agg": monthly_agg,
        "heatmap_12w": heatmap_12w,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1, separators=(",", ":"))
    kb = os.path.getsize(OUT_PATH) / 1024
    print(f"summary.json 寫入: {kb:.1f} KB")
    print(f"  月份: {len(months_desc)} 個, 全期 PnL={summary['totals']['pnl']}, 勝率={summary['totals']['win_rate']}%, Sharpe={metrics['sharpe']}, PF={metrics['profit_factor']}")


if __name__ == "__main__":
    main()
