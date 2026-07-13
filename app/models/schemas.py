from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


# ── Market Data ──

class OHLCVPoint(BaseModel):
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    @field_validator("high")
    @classmethod
    def high_ge_low(cls, v, info):
        l = info.data.get("low")
        if l is not None and v < l:
            raise ValueError("high must be >= low")
        return v

    @field_validator("volume")
    @classmethod
    def volume_nonneg(cls, v):
        if v < 0:
            raise ValueError("volume must be >= 0")
        return v


class SymbolInfo(BaseModel):
    symbol: str
    market: str = "crypto"
    exchange: str = ""
    base_asset: str = ""
    quote_asset: str = ""


# ── Strategy ──

class StrategyConfig(BaseModel):
    template_id: str
    params: dict[str, Any] = {}
    custom_code: str | None = None


class StrategyTemplate(BaseModel):
    id: str
    name: str
    description: str
    category: str
    params: list[dict] = []


class UserStrategyUpload(BaseModel):
    name: str
    description: str = ""
    category: str = "custom"
    code: str

class UserStrategyMeta(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = "custom"
    filename: str = ""
    created_at: str = ""
    status: str = "registered"
    params_space: dict[str, Any] = {}
    error: str | None = None


class BacktestConfig(BaseModel):
    strategy: StrategyConfig
    symbol: str
    timeframe: str = "1h"
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 100_000.0
    commission: float = 0.001
    slippage: float = 0.0005


# ── Results ──

class TradeRecord(BaseModel):
    entry_time: str
    entry_price: float
    exit_time: str | None = None
    exit_price: float | None = None
    size: float
    pnl: float | None = None
    pnl_pct: float | None = None


class MetricsOut(BaseModel):
    total_trades: int = 0
    win_rate: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    profit_factor: float = 0.0
    avg_trade: float = 0.0
    avg_winner: float = 0.0
    avg_loser: float = 0.0


class BacktestResultOut(BaseModel):
    task_id: str
    status: str = "completed"
    metrics: MetricsOut = Field(default_factory=MetricsOut)
    equity_curve: list[float] = []
    trades: list[TradeRecord] = []


class TaskStatus(BaseModel):
    task_id: str
    status: str = "running"
    progress: float = 0.0
    error: str | None = None


class AnalysisResultOut(BaseModel):
    task_id: str
    status: str = "completed"
    type: str = "walk_forward"
    summary: dict[str, Any] = {}
    details: dict[str, Any] = {}


# ── Optimize ──

class ParamRange(BaseModel):
    name: str
    min_val: float = 0.0
    max_val: float = 100.0
    step: float = 1.0
    type: str = "range"


class OptimizeConfig(BaseModel):
    strategy_id: str
    param_space: list[ParamRange] = []
    algorithm: str = "grid"
    max_trials: int = 100


class OptimizeResultOut(BaseModel):
    task_id: str
    status: str = "completed"
    best_params: dict[str, Any] = {}
    best_score: float = 0.0
    trials: list[dict] = []