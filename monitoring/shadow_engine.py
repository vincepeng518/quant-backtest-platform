from __future__ import annotations

import sqlite3
import logging
from dataclasses import dataclass, field
from typing import Optional

from monitoring.deviation import DeviationCalculator
from monitoring.orderbook import BookSnapshot, OrderBookSource

logger = logging.getLogger(__name__)


@dataclass
class PhaseConfig:
    # Phase 2: 時間鎖定
    min_secs_to_close: int = 150
    max_secs_to_close: int = 200
    # Phase 2: 賠率/成本控制
    odds_min: float = 0.60
    odds_max: float = 0.75
    # Phase 2: 深度檢測 (目標價位需有足夠掛單量支撐單次資金)
    min_depth_shares: float = 1000.0
    # Phase 3: 異常行情 (秒級成交量爆發 / 短線波動)
    anomaly_vol_mult: float = 4.0
    anomaly_lookback: int = 30
    # Phase 1: 偏離
    dev_base_points: float = 25.0


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
    # phase 4 tail snapshots
    tail: list = field(default_factory=list)


class ShadowEngine:
    """4 階段監聽 + 影子交易引擎。

    Phase 1: 雙端報價 (Binance WS + 訂單簿源) -> DeviationCalculator
    Phase 2: 時間鎖定 + 賠率/深度過濾
    Phase 3: 異常 -> 影子交易 (不發真單, 記 DB)
    Phase 4: 結算 + 尾盤快照 + 自動覆盤
    """

    def __init__(self, db_path: str, cfg: PhaseConfig | None = None,
                 book_source: Optional[OrderBookSource] = None) -> None:
        self.cfg = cfg or PhaseConfig()
        self.book = book_source
        self.dev = DeviationCalculator(base_points=self.cfg.dev_base_points)
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(open("monitoring/schema.sql").read())
        self.conn.commit()
        self.rounds: dict[str, RoundState] = {}
        self._vol_history: list[float] = []
        self._last_price: float = 0.0

    # ---- Phase 1: 報價接入 ----
    def on_spot(self, price: float, ts: float, market: str = "BTC-5m") -> None:
        self._last_price = price
        # 波動/成交量代理 (這裡用價格跳變幅度近似)
        if len(self._vol_history) >= 2:
            jump = abs(price - self._vol_history[-1])
            self._vol_history.append(jump)
        else:
            self._vol_history.append(0.0)
        if len(self._vol_history) > self.cfg.anomaly_lookback:
            self._vol_history.pop(0)
        # 偏離評估 (target=None -> 用移動均值偏離)
        ev = self.dev.evaluate(price)
        # 輪次路由
        rid = self._current_round_id(ts, market)
        st = self.rounds.setdefault(rid, RoundState(
            round_id=rid, market=market, open_ts=ts - (ts % 300), close_ts=ts - (ts % 300) + 300,
            open_price=price))
        st.window_drop_pct = (st.open_price - price) / st.open_price * 100.0
        # 尾盤快照 (Phase 4) — 即時持久化
        secs_left = st.close_ts - ts
        if 10 <= secs_left <= 20:
            self.conn.execute(
                "INSERT INTO tail_snapshots (round_id, snap_ts, secs_to_close, price) VALUES (?,?,?,?)",
                (rid, _iso(ts), int(secs_left), price))
            self.conn.commit()
        # 主判定
        self._evaluate(rid, st, price, ts, ev)

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

    # ---- Phase 2+3: 判定與執行 ----
    def _evaluate(self, rid: str, st: RoundState, price: float, ts: float, dev: dict) -> None:
        if st.resolved:
            return
        secs_left = st.close_ts - ts
        # Phase 2: 時間鎖定
        in_window = self.cfg.min_secs_to_close <= secs_left <= self.cfg.max_secs_to_close
        # Phase 1: 偏離觸發
        dev_trig = dev.get("triggered", False)
        # 價格偏低(BELOW) => 預期回拉 => 押 UP；偏高(ABOVE) => 押 DOWN
        direction = dev.get("direction")
        if direction == "BELOW":
            side = "UP"
        elif direction == "ABOVE":
            side = "DOWN"
        else:
            side = None
        if not (in_window and dev_trig and side):
            return

        # 取訂單簿 (Phase 2: 賠率 + 深度)
        book: Optional[BookSnapshot] = None
        if self.book:
            book = self.book.fetch_book(rid)
        odds_ok = True
        depth_ok = True
        if book:
            # 賠率帶: 買方吃單價 (ask for UP) 落 0.60-0.75
            odds_ok = self.cfg.odds_min <= book.ask <= self.cfg.odds_max
            depth_ok = book.depth_at_60_75 >= self.cfg.min_depth_shares
        anomaly = self._anomaly()
        # Phase 3: 異常 or 深度不足 -> 影子
        if anomaly or not depth_ok:
            entry_type = "SHADOW"
            reason = "anomaly" if anomaly else "low_depth"
        else:
            entry_type = "LIVE" if odds_ok else "SHADOW"
            reason = "odds_out_of_band" if not odds_ok else "ok"

        self._record_signal(rid, st, price, ts, secs_left, side, entry_type,
                            book.depth_at_60_75 if book else 0.0, depth_ok, anomaly, reason)
        # 標記本輪已下注 (避免重複)
        st.resolved = True

    def _record_signal(self, rid, st, price, ts, secs_left, side, entry_type,
                       depth, depth_ok, anomaly, reason) -> None:
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

    # ---- Phase 4: 結算與覆盤 ----
    def settle_round(self, rid: str, settle_price: float) -> None:
        st = self.rounds.get(rid)
        if not st or st.resolved is None:
            return
        # 找該輪信號
        cur = self.conn.execute(
            "SELECT id, side, sim_buy_cost, entry_type FROM shadow_trades WHERE round_id=? ORDER BY id DESC LIMIT 1",
            (rid,))
        row = cur.fetchone()
        if row:
            tid, side, cost, etype = row
            # UP 贏: settle>cost ; DOWN 贏: settle<cost (以現價代理)
            win = (settle_price > cost) if side == "UP" else (settle_price < cost)
            pnl = (settle_price - cost) if side == "UP" else (cost - settle_price)
            self.conn.execute(
                "UPDATE shadow_trades SET settle_price=?, pnl=?, win=? WHERE id=?",
                (settle_price, round(pnl, 2), 1 if win else 0, tid))
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()


def _iso(ts: float) -> str:
    import datetime
    return datetime.datetime.utcfromtimestamp(ts).isoformat() + "Z"
