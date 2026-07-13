from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import os
from typing import Optional

import pytest

from monitoring.shadow_engine import ShadowEngine, PhaseConfig
from monitoring.orderbook import BookSnapshot, OrderBookSource


class FakeBook(OrderBookSource):
    """可控訂單簿：depth_ok=False 時模擬流動性不足。"""
    def __init__(self, depth: float, ask: float = 0.65):
        self.depth = depth
        self.ask = ask
    def fetch_book(self, market_id: str = ""):
        return BookSnapshot(bid=self.ask-0.01, ask=self.ask, bid_size=5000,
                            ask_size=5000, spread=0.01, depth_at_60_75=self.depth)


def _make_engine(book: Optional[OrderBookSource], tmp: str, cfg: PhaseConfig | None = None):
    eng = ShadowEngine(tmp, cfg=cfg or PhaseConfig(dev_base_points=5.0), book_source=book)
    return eng


def test_deviation_trigger_and_shadow_record():
    """模擬現價跌破目標 -> 窗口內 -> 影子/實盤記錄。"""
    tmp = tempfile.mktemp(suffix=".db")
    # 流動性充足 -> 非影子 (若 odds_ok)
    book = FakeBook(depth=5000, ask=0.65)
    cfg = PhaseConfig(min_secs_to_close=150, max_secs_to_close=200,
                      odds_min=0.60, odds_max=0.75, min_depth_shares=1000,
                      dev_base_points=5.0)
    eng = _make_engine(book, tmp, cfg)
    # 時間軸: round 起點 t0=300 (close_ts=600), 窗口 150-200s => t in [400,450]
    # 先餵平穩價建立基線
    base = 64000.0
    for i in range(60):
        eng.on_spot(base, 300 + i, market="T")
    # 在 t=420 (secs_left=180, 窗口內) 砸盤 -30 點 (偏離觸發)
    eng.on_spot(base - 30, 420, market="T")
    conn = sqlite3.connect(tmp)
    rows = conn.execute("SELECT side, entry_type, seconds_to_close, book_depth FROM shadow_trades").fetchall()
    assert len(rows) == 1, f"expected 1 signal, got {rows}"
    side, etype, stc, depth = rows[0]
    assert side == "UP"           # 現價低於基線 -> 預期回拉 UP
    assert etype == "LIVE"        # 流動性足 + odds 在帶內
    assert stc == 180
    assert depth == 5000
    # 結算 (Phase 4): 拉回到 base+5 -> UP 贏
    eng.settle_round("T:1", base + 5)
    row = conn.execute("SELECT pnl, win FROM shadow_trades").fetchone()
    assert row[1] == 1            # win
    assert row[0] > 0
    eng.close()


def test_low_depth_goes_shadow():
    tmp = tempfile.mktemp(suffix=".db")
    book = FakeBook(depth=10, ask=0.65)  # 深度不足
    cfg = PhaseConfig(min_secs_to_close=150, max_secs_to_close=200,
                      odds_min=0.60, odds_max=0.75, min_depth_shares=1000,
                      dev_base_points=5.0)
    eng = _make_engine(book, tmp, cfg)
    base = 64000.0
    for i in range(60):
        eng.on_spot(base, 300 + i, market="T")
    eng.on_spot(base - 30, 420, market="T")
    conn = sqlite3.connect(tmp)
    rows = conn.execute("SELECT entry_type, liquidity_ok FROM shadow_trades").fetchall()
    assert rows[0][0] == "SHADOW"
    assert rows[0][1] == 0
    eng.close()


def test_out_of_window_no_signal():
    tmp = tempfile.mktemp(suffix=".db")
    book = FakeBook(depth=5000, ask=0.65)
    cfg = PhaseConfig(min_secs_to_close=150, max_secs_to_close=200,
                      odds_min=0.60, odds_max=0.75, min_depth_shares=1000,
                      dev_base_points=5.0)
    eng = _make_engine(book, tmp, cfg)
    base = 64000.0
    for i in range(60):
        eng.on_spot(base, 300 + i, market="T")
    # t=350 (secs_left=250) 窗口外 -> 不應有信號
    eng.on_spot(base - 30, 350, market="T")
    conn = sqlite3.connect(tmp)
    assert conn.execute("SELECT COUNT(*) FROM shadow_trades").fetchone()[0] == 0
    eng.close()


def test_tail_snapshot_recorded():
    tmp = tempfile.mktemp(suffix=".db")
    book = FakeBook(depth=5000, ask=0.65)
    cfg = PhaseConfig(min_secs_to_close=150, max_secs_to_close=200,
                      odds_min=0.60, odds_max=0.75, min_depth_shares=1000,
                      dev_base_points=5.0)
    eng = _make_engine(book, tmp, cfg)
    base = 64000.0
    for i in range(80):
        eng.on_spot(base, 520 + i, market="T")  # round T:1 close_ts=600; 580-590 => secs_left 10-20
    conn = sqlite3.connect(tmp)
    tails = conn.execute("SELECT COUNT(*) FROM tail_snapshots WHERE round_id='T:1'").fetchone()[0]
    assert tails > 0, "tail snapshot (Phase 4) should be recorded in last 10-20s"
    eng.close()
