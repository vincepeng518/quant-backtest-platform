#!/usr/bin/env python3
"""網格模擬倉 (paper trading) — 現在不跑, 等高波動再啟動。

狀態: 已寫好未啟用。今日 nATR 0.0250 < 門檻 0.0391 -> 引擎回 FLAT, 啟動了也只會空手等待。

啟動時機
--------
每日 cron 推播「網格切換 不開網格 → 中性/只做多/只做空網格」時, 才執行:
    cd /root/Crypto-Backtesting-Lab
    ./venv/bin/python scripts/grid_paper.py --start

之後讓它常駐 (每 60 秒抓一次現價):
    ./venv/bin/python scripts/grid_paper.py --run

設計要點
--------
- 撮合完全複用 engine/grid_core.GridState, 與回測同一份程式碼
  (tests/test_grid_core_matches_backtest.py 已斷言數字完全相同)。
- 每日重讀 grid_switcher 信號: FLAT -> 平倉停機; 模式改變 -> 重建網格。
- 狀態持久化到 runtime/grid_paper_state.json, 進程重啟不遺失倉位。
- 不碰任何交易所私鑰, 純讀公開行情。
"""
from __future__ import annotations

import os
import sys
import json
import time
import argparse
import datetime as dt

ROOT = "/root/Crypto-Backtesting-Lab"
VENV_PY = os.path.join(ROOT, "venv", "bin", "python")
if os.path.exists(VENV_PY) and os.path.realpath(sys.executable) != os.path.realpath(VENV_PY):
    os.execv(VENV_PY, [VENV_PY, os.path.abspath(__file__)] + sys.argv[1:])

sys.path.insert(0, ROOT)
os.environ.setdefault("PROJECT_ROOT", ROOT)

from engine.grid_core import GridState  # noqa: E402

STATE_PATH = os.path.join(ROOT, "runtime", "grid_paper_state.json")
LOG_PATH = os.path.join(ROOT, "runtime", "grid_paper_fills.jsonl")
SYMBOL = "BTC/USDT:USDT"

FIELDS = ("center", "half_range", "spacing", "lo_b", "hi_b", "anchor",
          "cash", "pos", "fees_paid", "funding_paid",
          "n_trades", "n_recenter", "n_flat", "armed", "regime",
          "n_grids", "qty", "fee_bps", "taker_bps", "recenter_gap", "cap_btc")


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def load_state() -> tuple[GridState, dict]:
    g = GridState()
    meta = {"mode": "", "started_at": None, "peak_equity": 0.0}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            d = json.load(f)
        for k in FIELDS:
            if k in d:
                setattr(g, k, d[k])
        meta.update(d.get("_meta", {}))
    return g, meta


def save_state(g: GridState, meta: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    d = {k: getattr(g, k) for k in FIELDS}
    d["_meta"] = meta
    d["_saved_at"] = now()
    with open(STATE_PATH, "w") as f:
        json.dump(d, f, indent=2)


def log_fills(fills: list, mode: str) -> None:
    if not fills:
        return
    with open(LOG_PATH, "a") as f:
        for fl in fills:
            f.write(json.dumps({
                "time": now(), "mode": mode, "side": fl.side,
                "price": round(fl.price, 2), "qty": fl.qty,
                "fee": round(fl.fee, 6), "anchor": fl.anchor,
            }) + "\n")


def get_price() -> float:
    import ccxt
    ex = ccxt.bingx({"enableRateLimit": True})
    return float(ex.fetch_ticker(SYMBOL)["last"])


def get_signal():
    from engine.strategies.grid_switcher import latest_signal
    return latest_signal()


def sync_signal(g: GridState, meta: dict, price: float, verbose: bool = True) -> None:
    """依當前引擎信號調整網格狀態。"""
    sig, close, bar_date = get_signal()
    mode = sig.mode
    prev = meta.get("mode", "")

    if mode == "flat":
        if g.armed:
            g.flatten(price)
            if verbose:
                print(f"[{now()}] 信號 FLAT -> 平倉停機, 權益 {g.equity(price):.2f}")
        meta["mode"] = mode
        return

    regime = {"long": 1, "short": -1, "range": 0}[mode]
    if (not g.armed) or mode != prev:
        g.regime = regime
        g.n_grids = sig.geometry["n_grids"]
        g.recenter_gap = sig.geometry["recenter_gap"]
        g.build(price, sig.geometry["half_range"])
        if meta.get("started_at") is None:
            meta["started_at"] = now()
        if verbose:
            gm = sig.geometry
            print(f"[{now()}] 建立網格 {mode.upper()} @ {price:,.0f}")
            print(f"  區間 {gm['lower']:,.0f} ~ {gm['upper']:,.0f} | "
                  f"{gm['n_grids']} 格 | 格距 {gm['spacing']:,.0f} ({gm['spacing_pct']:.2f}%)")
    meta["mode"] = mode


def cmd_start(args) -> int:
    g, meta = load_state()
    if g.cap_btc is None:
        g.cap_btc = args.cap
        g.qty = args.qty
    price = get_price()
    sync_signal(g, meta, price)
    if not g.armed:
        print(f"[{now()}] 目前信號 FLAT — 未建網格。等高波動再跑一次 --start。")
    save_state(g, meta)
    return 0


def cmd_run(args) -> int:
    g, meta = load_state()
    if g.cap_btc is None:
        g.cap_btc = args.cap
        g.qty = args.qty
    last_sig_day = ""
    print(f"[{now()}] 模擬倉啟動, 每 {args.interval}s 抓價 (Ctrl-C 停止)")
    while True:
        try:
            price = get_price()
            today = dt.date.today().isoformat()
            if today != last_sig_day:
                sync_signal(g, meta, price)
                last_sig_day = today
            fills = g.on_price(price)
            log_fills(fills, meta.get("mode", ""))
            g.settle(price)
            eq = g.equity(price)
            meta["peak_equity"] = max(meta.get("peak_equity", 0.0), eq)
            if fills:
                for fl in fills:
                    print(f"[{now()}] {fl.side.upper():4s} {fl.qty} @ {fl.price:,.2f}")
                print(f"           倉位 {g.pos:+.4f} BTC | 權益 {eq:+.2f} | 累計 {g.n_trades} 筆")
            save_state(g, meta)
        except KeyboardInterrupt:
            print(f"\n[{now()}] 停止。狀態已保存, 倉位 {g.pos:+.4f} BTC")
            save_state(g, meta)
            return 0
        except Exception as e:
            print(f"[{now()}] 錯誤 {type(e).__name__}: {e}")
        time.sleep(args.interval)


def cmd_status(args) -> int:
    g, meta = load_state()
    if not os.path.exists(STATE_PATH):
        print("模擬倉尚未啟動 (無狀態檔)。")
        return 0
    price = get_price()
    eq = g.equity(price)
    peak = meta.get("peak_equity", 0.0)
    print(f"模式       {meta.get('mode') or '(未設定)'}  {'運行中' if g.armed else '停機'}")
    print(f"啟動於     {meta.get('started_at') or '-'}")
    print(f"BTC 現價   {price:,.2f}")
    if g.armed:
        print(f"網格區間   {g.lo_b:,.0f} ~ {g.hi_b:,.0f} | 格距 {g.spacing:,.0f}")
    print(f"倉位       {g.pos:+.4f} BTC  (名義 ${g.notional(price):,.0f})")
    print(f"權益       {eq:+.2f}   峰值 {peak:+.2f}   回撤 {eq - peak:+.2f}")
    print(f"成交       {g.n_trades} 筆 | 手續費 {g.fees_paid:.2f} | 資金費 {-g.funding_paid:+.2f}")
    print(f"重置       {g.n_recenter} 次 | 平倉 {g.n_flat} 次")
    return 0


def cmd_reset(args) -> int:
    for p in (STATE_PATH, LOG_PATH):
        if os.path.exists(p):
            os.remove(p)
    print("模擬倉狀態已清空。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="網格模擬倉")
    ap.add_argument("--qty", type=float, default=0.0023, help="每格數量 BTC")
    ap.add_argument("--cap", type=float, default=0.20, help="倉位上限 BTC")
    ap.add_argument("--interval", type=int, default=60, help="抓價間隔秒")
    sub = ap.add_subparsers(dest="cmd")
    for name, fn in (("start", cmd_start), ("run", cmd_run),
                     ("status", cmd_status), ("reset", cmd_reset)):
        sp = sub.add_parser(name)
        sp.set_defaults(func=fn)
    # 同時支援 --start / --run / --status 形式
    for flag in ("--start", "--run", "--status", "--reset"):
        ap.add_argument(flag, action="store_true")
    args = ap.parse_args()

    if getattr(args, "cmd", None):
        return args.func(args)
    for name, fn in (("start", cmd_start), ("run", cmd_run),
                     ("status", cmd_status), ("reset", cmd_reset)):
        if getattr(args, name, False):
            return fn(args)
    return cmd_status(args)


if __name__ == "__main__":
    sys.exit(main())
