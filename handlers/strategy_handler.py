"""
策略 handler：接收 BarEvent，產出 SignalEvent

兩種模式：
1. 動態策略（execute_user_strategy）：從 strategy_code 執行策略
2. 預算 series 模式：直接用預先算好的 entries/exits series
"""
from __future__ import annotations

from typing import List, Optional
import pandas as pd
import numpy as np

from events import BarEvent, Event, SignalEvent, SignalType
from handlers import EventHandler


class StrategyHandler(EventHandler):
    """
    策略 handler

    支援兩種初始化方式：
    1. set_dynamic_strategy(code, params, df)：策略代碼動態執行
    2. set_precomputed_signals(entries, exits, long_entries, ...)：用預算 series
    """

    def __init__(self):
        self._strategy_code: Optional[str] = None
        self._params: dict = {}
        self._df: Optional[pd.DataFrame] = None

        # 預算模式
        self._entries: Optional[pd.Series] = None
        self._exits: Optional[pd.Series] = None
        self._long_entries: Optional[pd.Series] = None
        self._long_exits: Optional[pd.Series] = None
        self._short_entries: Optional[pd.Series] = None
        self._short_exits: Optional[pd.Series] = None

        self._mode = "none"  # "dynamic" or "precomputed"

    def set_dynamic_strategy(self, code: str, params: dict, df: pd.DataFrame) -> None:
        self._strategy_code = code
        self._params = params
        self._df = df
        self._mode = "dynamic"

    def set_precomputed_signals(
        self,
        entries: pd.Series,
        exits: pd.Series,
        long_entries: Optional[pd.Series] = None,
        long_exits: Optional[pd.Series] = None,
        short_entries: Optional[pd.Series] = None,
        short_exits: Optional[pd.Series] = None,
    ) -> None:
        self._entries = entries.astype(bool).fillna(False)
        self._exits = exits.astype(bool).fillna(False)
        self._long_entries = (
            long_entries.astype(bool).fillna(False)
            if long_entries is not None
            else self._entries
        )
        self._long_exits = (
            long_exits.astype(bool).fillna(False)
            if long_exits is not None
            else self._exits
        )
        self._short_entries = (
            short_entries.astype(bool).fillna(False)
            if short_entries is not None
            else pd.Series(False, index=entries.index)
        )
        self._short_exits = (
            short_exits.astype(bool).fillna(False)
            if short_exits is not None
            else pd.Series(False, index=entries.index)
        )
        self._mode = "precomputed"

    def handle(self, event: Event) -> List[Event]:
        if not isinstance(event, BarEvent):
            return []

        if self._mode == "precomputed":
            return self._handle_precomputed(event)
        elif self._mode == "dynamic":
            return self._handle_dynamic(event)
        return []

    def _handle_precomputed(self, event: BarEvent) -> List[SignalEvent]:
        """預算模式：直接查 series"""
        try:
            idx = self._entries.index.get_loc(event.timestamp)
        except KeyError:
            return []

        signals = []
        if bool(self._long_entries.iloc[idx]):
            signals.append(SignalEvent(
                timestamp=event.timestamp,
                signal_type=SignalType.LONG_ENTRY,
            ))
        if bool(self._long_exits.iloc[idx]):
            signals.append(SignalEvent(
                timestamp=event.timestamp,
                signal_type=SignalType.LONG_EXIT,
            ))
        if bool(self._short_entries.iloc[idx]):
            signals.append(SignalEvent(
                timestamp=event.timestamp,
                signal_type=SignalType.SHORT_ENTRY,
            ))
        if bool(self._short_exits.iloc[idx]):
            signals.append(SignalEvent(
                timestamp=event.timestamp,
                signal_type=SignalType.SHORT_EXIT,
            ))
        return signals

    def _handle_dynamic(self, event: BarEvent) -> List[SignalEvent]:
        """動態模式：執行策略代碼"""
        from strategies.strategy_runner import execute_user_strategy

        if self._df is None:
            return []

        try:
            idx = self._df.index.get_loc(event.timestamp)
        except KeyError:
            return []

        sub_df = self._df.iloc[: idx + 1]
        result = execute_user_strategy(self._strategy_code, sub_df, self._params)
        if not isinstance(result, tuple) or len(result) not in (3, 7):
            return []

        if len(result) == 7:
            _, _, err, le, lx, se, sx = result
        else:
            _, _, err = result
            le = lx = se = sx = pd.Series(False, index=sub_df.index)

        if err:
            return []

        signals = []
        if bool(le.iloc[idx]):
            signals.append(SignalEvent(event.timestamp, SignalType.LONG_ENTRY))
        if bool(lx.iloc[idx]):
            signals.append(SignalEvent(event.timestamp, SignalType.LONG_EXIT))
        if bool(se.iloc[idx]):
            signals.append(SignalEvent(event.timestamp, SignalType.SHORT_ENTRY))
        if bool(sx.iloc[idx]):
            signals.append(SignalEvent(event.timestamp, SignalType.SHORT_EXIT))
        return signals
