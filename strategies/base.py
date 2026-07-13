from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd


@dataclass
class Bar:
    timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float
    mark_price: Optional[float] = None


@dataclass
class Signal:
    action: str  # 'buy' | 'sell' | 'close' | 'close_buy' | 'close_sell'
    price: Optional[float] = None
    quantity: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    metadata: Optional[dict] = None
    order_type: str = "market"


@dataclass
class Position:
    size: float
    entry_price: float
    current_price: float
    pnl: float = 0.0
    pnl_pct: float = 0.0


class StrategyBase(ABC):
    """所有策略的抽象基類。"""

    name: str = "base"
    description: str = ""
    category: str = ""

    def __init__(self) -> None:
        self.position: Optional[Position] = None
        self.params: dict[str, Any] = {}
        self.equity_curve: list[float] = []

    @abstractmethod
    def init(self, params: dict[str, Any]) -> None:
        self.params = params

    @abstractmethod
    def next(self, bar: Bar) -> Optional[Signal]:
        ...

    def get_params(self) -> dict[str, Any]:
        return dict(self.params)

    def get_params_space(self) -> dict[str, Any]:
        return {}

    def warmup_period(self) -> int:
        return 0

    # ── ML 接口預留 ──

    def predict(self, features: np.ndarray) -> float:
        raise NotImplementedError("ML prediction not enabled for this strategy")

    def load_model(self, model_path: str) -> None:
        raise NotImplementedError("ML model loading not enabled for this strategy")