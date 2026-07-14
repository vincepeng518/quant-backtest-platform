from __future__ import annotations

import sqlite3
import logging
import datetime
import time
import os
from dataclasses import dataclass, field
from typing import Optional

from monitoring.deviation import DeviationCalculator
from monitoring.orderbook import BookSnapshot, OrderBookSource, PolymarketClobSource
from monitoring.config import MonitorConfig

logger = logging.getLogger(__name__)


@dataclass
class PhaseConfig:
    min_secs_to_close: int
    max_secs_to_close: int
    odds_min: float
    odds_max: float
    min_depth_shares: float
    anomaly_vol_mult: float
    anomaly_lookback: int
    dev_base_points: float
    tail_min: int = 10
    tail_max: int = 20


@dataclass
class RoundState:
    round_id: str
    market: str
    open_ts: float
    close_ts: float
    open_price: float
    window_drop_pct: float = 0.0
    rsi: Optional[float] = None
    resolved: bool = False
    settled: bool = False


class ShadowEngine:
    """4 階段監聽 + 影子交易引擎 (穩健版)。

    Phase 1: 雙端報價 (Binance WS + 訂單簿源) -> DeviationCalculator
    Phase 2: 時間鎖定 + 賠率/深度過濾
    Phase 3: 異常 -> 影子交易 (不發真單, 記 DB)
    Phase 4: 結算 + 尾盤快照 + 自動覆盤
    """

    def __init__(self, cfg: MonitorConfig, book_source: Optional[OrderBookSource] = None,
                 target_provider=None) -> None:
        """target_provider: callable(market_id) -> Optional[float]
        返回該輪次的真實 startPrice (Phase 1 目標價真值)。
        None -> 回退 Binance 輪次開盤價近似。
        """
        self.cfg_model = cfg
        self.cfg = PhaseConfig(
            min_secs_to_close=cfg.min_secs_to_close,
            max_secs_to_close=cfg.max_secs_to_close,
            odds_min=cfg.odds_min, odds_max=cfg.odds_max,
            min_depth_shares=cfg.min_depth_shares,
            anomaly_vol_mult=cfg.anomaly_vol_mult,
            anomaly_lookback=cfg.anomaly_lookback,
            dev_base_points=cfg.dev_base_points,
            tail_min=cfg.tail_min, tail_max=cfg.tail_max,
        )
        self.book = book_source
        self.target_provider = target_provider
        self.dev = DeviationCalculator(
            base_points=cfg.dev_base_points, min_points=cfg.dev_min_points,
            max_points=cfg.dev_max_points, vol_mult=cfg.dev_vol_mult, window=cfg.dev_window)
        self.conn = sqlite3.connect(cfg.db, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        _schema = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "monitoring", "schema.sql")
        self.conn.executescript(open(_schema).read())
        self.conn.commit()
        self.rounds: dict[str, RoundState] = {}
        self._vol_history: list[float] = []
        self._last_price: float = 0.0
        # 訂單簿快取 (降級: 失敗不崩, 用上次成功值或 None)
        self._book_cache: Optional[BookSnapshot] = None
        self._book_cache_ts: float = 0.0
        self._book_failures: int = 0

    # ---- Phase 1: 報價接入 ----
    def on_spot(self, price: float, ts: float, market: str = "BTC-5m") -> None:
        self._last_price = price
        # 波動代理: 價格跳變幅度
        if len(self._vol_history) >= 1:
            jump = abs(price - self._vol_history[-1])
        else:
            jump = 0.0
        self._vol_history.append(jump)
        if len(self._vol_history) > self.cfg.anomaly_lookback:
            self._vol_history.pop(0)
        # 偏離評估
        ev = self.dev.evaluate(price)
        # 輪次路由
        rid = self._current_round_id(ts, market)
        is_new = rid not in self.rounds
        st = self.rounds.setdefault(rid, RoundState(
            round_id=rid, market=market, open_ts=ts - (ts % 300),
            close_ts=ts - (ts % 300) + 300, open_price=price))
        if is_new and self.target_provider is not None:
            # Phase 1 真值: 用 REST 輪次 startPrice 當目標價 (取代 Binance 開盤近似)
            try:
                tp = self.target_provider(market)
                if tp is not None:
                    st.open_price = tp
            except Exception as e:
                logger.warning("[ENGINE] target_provider failed: %s", e)
        st.window_drop_pct = (st.open_price - price) / st.open_price * 100.0
        # 尾盤快照 (Phase 4) — 即時持久化
        secs_left = st.close_ts - ts
        if self.cfg.tail_min <= secs_left <= self.cfg.tail_max:
            self._persist_tail(rid, ts, int(secs_left), price)
        # 主判定
        self._evaluate(rid, st, price, ts, ev)
        # 自動結算到期輪次 (Phase 4, 無人值守)
        if self.cfg_model.settle_on_close:
            self._settle_due(ts)

    def _settle_due(self, now_ts: float) -> None:
        """每個 tick 檢查有無輪次已到期未結算 -> 用輪次收盤現價當結算價。"""
        for rid, st in list(self.rounds.items()):
            if not st.settled and now_ts >= st.close_ts:
                self.settle_round(rid, self._last_price)
                st.settled = True

    def _current_round_id(self, ts: float, market: str) -> str:
        return f"{market}:{int(ts // 300)}"

    def _anomaly(self) -> bool:
        if len(self._vol_history) < self.cfg.anomaly_lookback:
            return False
        import statistics
        recent = self._vol_history[-self.cfg.anomaly_lookback:]
        mean = statistics.mean(recent)
        std = statistics.pstdev(recent) or 1e-9
        last = recent[-1]
        return last > self.cfg.anomaly_vol_mult * (mean + std)

    # ---- 訂單簿 (帶快取 + 降級) ----
    def _get_book(self, st: "RoundState") -> Optional[BookSnapshot]:
        if not self.book:
            return None
        now = time.time()
        if self._book_cache and (now - self._book_cache_ts) < self.cfg_model.ob_refresh_sec:
            return self._book_cache
        try:
            # 用 predict.fun 市場 id (st.market) 拉訂單簿, 非組合的 round_id
            b = self.book.fetch_book(st.market)
            if b:
                self._book_cache = b
                self._book_cache_ts = now
                self._book_failures = 0
                return b
        except Exception as e:
            self._book_failures += 1
            logger.warning("book fetch fail x%d: %s", self._book_failures, e)
        return self._book_cache  # 降級: 用舊值 (可能 None)

    # ---- Phase 2+3: 判定與執行 ----
    def _evaluate(self, rid: str, st: RoundState, price: float, ts: float, dev: dict) -> None:
        if st.resolved:
            return
        secs_left = st.close_ts - ts
        in_window = self.cfg.min_secs_to_close <= secs_left <= self.cfg.max_secs_to_close
        dev_trig = dev.get("triggered", False)
        direction = dev.get("direction")
        if direction == "BELOW":
            side = "UP"
        elif direction == "ABOVE":
            side = "DOWN"
        else:
            side = None
        if not (in_window and dev_trig and side):
            return

        book = self._get_book(st)
        odds_ok = True
        depth_ok = True
        if book:
            odds_ok = self.cfg.odds_min <= book.ask <= self.cfg.odds_max
            depth_ok = book.depth_at_60_75 >= self.cfg.min_depth_shares
        anomaly = self._anomaly()
        if anomaly or not depth_ok:
            entry_type = "SHADOW"
            reason = "anomaly" if anomaly else "low_depth"
        else:
            entry_type = "LIVE" if odds_ok else "SHADOW"
            reason = "odds_out_of_band" if not odds_ok else "ok"

        self._record_signal(rid, st, price, ts, secs_left, side, entry_type,
                            book.depth_at_60_75 if book else 0.0, depth_ok, anomaly, reason)
        st.resolved = True

    def _record_signal(self, rid, st, price, ts, secs_left, side, entry_type,
                       depth, depth_ok, anomaly, reason) -> None:
        try:
            self.conn.execute(
                """INSERT INTO shadow_trades
                   (round_id, market, signal_ts, seconds_to_close, side, entry_type,
                    sim_buy_cost, book_depth, liquidity_ok, anomaly_flag, note)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (rid, st.market, _iso(ts), int(secs_left), side, entry_type,
                 price, depth, 1 if depth_ok else 0, 1 if anomaly else 0, reason))
            self.conn.commit()
            logger.info("[SIGNAL] %s %s @%.2f secs_left=%d type=%s reason=%s",
                        rid, side, price, secs_left, entry_type, reason)
        except Exception as e:
            logger.error("record_signal failed: %s", e)

    def _persist_tail(self, rid, ts, secs_left, price) -> None:
        try:
            self.conn.execute(
                "INSERT INTO tail_snapshots (round_id, snap_ts, secs_to_close, price) VALUES (?,?,?,?)",
                (rid, _iso(ts), secs_left, price))
            self.conn.commit()
        except Exception as e:
            logger.error("persist_tail failed: %s", e)

    # ---- Phase 4: 結算與覆盤 ----
    def settle_round(self, rid: str, settle_price: float) -> None:
        try:
            cur = self.conn.execute(
                "SELECT id, side, sim_buy_cost, entry_type FROM shadow_trades WHERE round_id=? ORDER BY id DESC LIMIT 1",
                (rid,))
            row = cur.fetchone()
            if row:
                tid, side, cost, etype = row
                win = (settle_price > cost) if side == "UP" else (settle_price < cost)
                pnl = (settle_price - cost) if side == "UP" else (cost - settle_price)
                self.conn.execute(
                    "UPDATE shadow_trades SET settle_price=?, pnl=?, win=? WHERE id=?",
                    (settle_price, round(pnl, 2), 1 if win else 0, tid))
                self.conn.commit()
                logger.info("[SETTLE] %s side=%s settle=%.2f win=%s pnl=%.2f",
                            rid, side, settle_price, win, pnl)
        except Exception as e:
            logger.error("settle_round failed: %s", e)

    def stats(self) -> dict:
        import sqlite3
        c = self.conn
        shadow = c.execute("SELECT COUNT(*) FROM shadow_trades").fetchone()[0]
        live = c.execute("SELECT COUNT(*) FROM shadow_trades WHERE entry_type='LIVE'").fetchone()[0]
        tail = c.execute("SELECT COUNT(*) FROM tail_snapshots").fetchone()[0]
        wins = c.execute("SELECT COUNT(*) FROM shadow_trades WHERE win=1").fetchone()[0]
        resolved = c.execute("SELECT COUNT(*) FROM shadow_trades WHERE win IS NOT NULL").fetchone()[0]
        return {
            "shadow_trades": shadow, "live": live, "tail_snapshots": tail,
            "resolved": resolved, "wins": wins,
            "win_rate": round(wins / resolved * 100, 1) if resolved else 0.0,
        }

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


def _iso(ts: float) -> str:
    return datetime.datetime.utcfromtimestamp(ts).isoformat() + "Z"
