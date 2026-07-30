#!/usr/bin/env python3
"""網格切換引擎 — 每日自動信號 + 變化推播。

用途: cron 每日 UTC 收盤後跑一次。
  - 跑 grid_switcher 引擎 -> 寫 runtime/strategy_status.json
  - 與上次信號比對, 只在「模式改變」時輸出推播內容 (無變化 -> 靜默)
  - 輸出到 stdout, 供 Hermes cron no_agent 模式直接投遞

靜默契約: 沒有輸出 = 沒有變化 = 不用看。
"""
from __future__ import annotations
import os, sys, json, datetime as dt

ROOT = "/root/Crypto-Backtesting-Lab"
VENV_PY = os.path.join(ROOT, "venv", "bin", "python")

# cron 用系統 python 執行, 缺 ccxt/pandas -> 自動改用專案 venv 重跑一次
if os.path.exists(VENV_PY) and os.path.realpath(sys.executable) != os.path.realpath(VENV_PY):
    os.execv(VENV_PY, [VENV_PY, os.path.abspath(__file__)] + sys.argv[1:])

sys.path.insert(0, ROOT)
os.environ.setdefault("PROJECT_ROOT", ROOT)

STATE = os.path.join(ROOT, "runtime", "grid_last_mode.json")

MODE_LABEL = {
    "flat":  "不開網格",
    "range": "中性網格",
    "long":  "只做多網格",
    "short": "只做空網格",
}


def read_last() -> str:
    try:
        with open(STATE) as f:
            return json.load(f).get("mode", "")
    except Exception:
        return ""


def write_last(mode: str, bar_date: str) -> None:
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump({"mode": mode, "bar_date": bar_date,
                   "at": dt.datetime.now().isoformat(timespec="seconds")}, f)


def main() -> int:
    from engine.strategies.grid_switcher import latest_signal, write_status

    try:
        sig, close, bar_date = latest_signal()
    except Exception as e:
        # 取數失敗要出聲, 否則靜默會掩蓋壞掉的引擎
        print(f"網格引擎執行失敗: {type(e).__name__}: {e}")
        return 1

    write_status(sig, close, bar_date)
    bd = str(bar_date)[:10]
    last = read_last()
    write_last(sig.mode, bd)

    if sig.mode == last:
        return 0  # 無變化 -> 靜默

    g = sig.geometry
    lines = [
        f"網格切換 {MODE_LABEL.get(last, last or '(初次)')} → {MODE_LABEL.get(sig.mode, sig.mode)}",
        f"BTC {close:,.0f} | 日線 {bd}",
        sig.reason,
    ]
    if sig.mode != "flat":
        lines += [
            "",
            f"區間 {g['lower']:,.0f} ~ {g['upper']:,.0f}",
            f"{g['n_grids']} 格 | 格距 {g['spacing']:,.0f} ({g['spacing_pct']:.2f}%)",
            f"價格離邊界 {g['recenter_gap']:,.0f} 內重置網格",
        ]
    else:
        lines += ["", "動作: 停掉現有網格, 平倉觀望。"]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
