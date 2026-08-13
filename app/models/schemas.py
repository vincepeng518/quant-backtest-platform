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
    name: str = ""


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


class FundingConfig(BaseModel):
    enabled: bool = False
    interval_hours: int = Field(default=8, ge=1, le=24 * 365)
    default_rate: float = Field(default=0.0001, ge=-1.0, le=1.0)

class PerpetualConfig(BaseModel):
    enabled: bool = False
    leverage: float = Field(default=1.0, ge=1.0, le=200.0)
    maintenance_margin_rate: float = Field(default=0.005, gt=0.0, lt=1.0)

class ExchangeConfig(BaseModel):
    enabled: bool = False
    maker_fee: float = Field(default=0.0002, ge=0.0, le=1.0)
    taker_fee: float = Field(default=0.0005, ge=0.0, le=1.0)
    latency_bars: int = Field(default=0, ge=0)
    book_base_slippage: float = Field(default=0.0005, ge=0.0, le=1.0)
    maker_probability: float = Field(default=0.0, ge=0.0, le=1.0)


class BacktestConfig(BaseModel):
    strategy: StrategyConfig
    symbol: str
    market: str = "crypto"  # crypto | equity | forex
    timeframe: str = "1h"
    source: str = "binance"  # data source: binance | bingx | csv | test | tradfi
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = Field(default=100_000.0, gt=0.0)
    commission: float = Field(default=0.001, ge=0.0, le=1.0)
    slippage: float = Field(default=0.0005, ge=0.0, le=1.0)
    funding: FundingConfig = Field(default_factory=FundingConfig)
    perpetual: PerpetualConfig = Field(default_factory=PerpetualConfig)
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    equity: dict = Field(default_factory=dict)
    forex: dict = Field(default_factory=dict)
    engine: str = "bar"  # bar | replay (tick-level intrabar execution)
    ticks_per_bar: int = Field(default=20, ge=1, le=10_000)  # replay engine: synthesized ticks per bar
    tick_seed: int | None = None  # replay engine: reproducible tick path
    exchanges: list[str] = Field(default_factory=list)  # multi-exchange execution (paper/live)

    @field_validator("initial_capital")
    @classmethod
    def _capital_finite(cls, v, info):
        import math
        if not math.isfinite(v):
            raise ValueError("initial_capital must be finite")
        if v > 1e12:
            raise ValueError("initial_capital too large (max 1e12)")
        return v

    @field_validator("source")
    @classmethod
    def _source_valid(cls, v):
        if v not in {"binance", "bingx", "csv", "test", "tradfi", "bingx_tradfi"}:
            raise ValueError(f"unsupported source: {v!r}")
        return v

    @field_validator("engine")
    @classmethod
    def _engine_valid(cls, v):
        if v not in {"bar", "replay"}:
            raise ValueError(f"unsupported engine: {v!r}")
        return v

    @field_validator("timeframe")
    @classmethod
    def _timeframe_valid(cls, v):
        import re
        if not re.fullmatch(r"^\d+[smhdwM]$", v):
            raise ValueError(f"invalid timeframe: {v!r}")
        return v


# ── Results ──

class TradeRecord(BaseModel):
    entry_time: str
    entry_price: float
    exit_time: str | None = None
    exit_price: float | None = None
    size: float
    pnl: float | None = None
    pnl_pct: float | None = None
    funding_paid: float | None = None
    liquidated: bool = False
    direction: str = "long"
    exit_reason: str = ""
    holding_bars: int = 0
    mae: float | None = None
    mfe: float | None = None


class MetricsOut(BaseModel):
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    profit_factor: float = 0.0
    avg_trade: float = 0.0
    avg_winner: float = 0.0
    avg_loser: float = 0.0
    net_profit: float = 0.0
    largest_loss: float = 0.0
    largest_loss_pct: float = 0.0
    largest_win: float = 0.0
    win_loss_ratio: float = 0.0
    expectancy: float = 0.0
    annual_return_pct: float = 0.0
    calmar_ratio: float = 0.0
    avg_holding_bars: float = 0.0
    trade_freq: float = 0.0
    # Long/Short split
    long_trades: int = 0
    short_trades: int = 0
    long_win_rate: float = 0.0
    short_win_rate: float = 0.0
    long_pnl: float = 0.0
    short_pnl: float = 0.0
    long_expectancy: float = 0.0
    short_expectancy: float = 0.0
    long_profit_factor: float = 0.0
    short_profit_factor: float = 0.0
    # ── Quality score (0-100) ──
    quality_score: float = 0.0
    quality_grade: str = "F"
    quality_breakdown: dict = {}


class BacktestResultOut(BaseModel):
    task_id: str
    status: str = "completed"
    config: dict = Field(default_factory=dict)
    metrics: MetricsOut = Field(default_factory=MetricsOut)
    equity_curve: list[dict] = []
    buy_hold_equity: list[dict] = []
    trades: list[TradeRecord] = []
    position_status: list[dict] = []


class TaskStatus(BaseModel):
    task_id: str
    status: str = "running"
    progress: float = 0.0
    stage: str = "loading"  # T2: 三階段(loading/backtesting/finalizing/completed/cancelled)
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
    min: float = 0.0
    max: float = 100.0
    step: float = Field(default=1.0, gt=0.0)
    type: str = "range"

    @field_validator("step")
    @classmethod
    def _step_finite_and_bounded(cls, v):
        import math
        if not math.isfinite(v):
            raise ValueError("step must be finite")
        # step too small (relative to range) expands the grid to a billion entries
        # -> memory DoS (step=1e-9 on [0,100] tried to allocate 7+ TiB). Floor it.
        if v < 1e-5:
            raise ValueError("step too small (min 1e-5)")
        return v

    @field_validator("max")
    @classmethod
    def _max_ge_min(cls, v, info):
        mn = info.data.get("min")
        if mn is not None and v < mn:
            raise ValueError("max must be >= min")
        if info.data.get("step"):
            _span = v - (mn or 0.0)
            if _span / info.data["step"] > 1_000_000:
                raise ValueError("param range / step produces too many points (max 1M)")
        return v


class OptimizeConfig(BaseModel):
    strategy_id: str
    param_space: list[ParamRange] = []
    algorithm: str = "grid"
    max_trials: int = Field(default=100, ge=1, le=10_000)
    # Engine realism (opt-in; disabled = legacy 1x spot)
    funding: FundingConfig = Field(default_factory=FundingConfig)
    perpetual: PerpetualConfig = Field(default_factory=PerpetualConfig)
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)


class OptimizeResultOut(BaseModel):
    task_id: str
    status: str = "completed"
    best_params: dict[str, Any] = {}
    best_score: float = 0.0
    trials: list[dict] = []
    grid: dict | None = None  # 2D grid matrix, populated only when param_space has exactly 2 range params


# ── Admin / Operator panel ──

class CredentialStatus(BaseModel):
    """Masked view of an external/exchange credential — NEVER exposes plaintext secret."""
    name: str
    kind: str  # exchange | data_source | infra
    configured: bool
    masked_value: str = ""   # e.g. "sk-****abcd" or "set" / "unset"
    updated_at: str | None = None


class MonitoredSymbol(BaseModel):
    symbol: str
    market: str = "crypto"
    exchange: str = ""
    description: str = ""
    pinned: bool = False
    added_at: str = ""


class TaskHistoryItem(BaseModel):
    task_id: str
    kind: str            # backtest | optimize | analysis
    status: str
    created_at: str
    symbol: str | None = None
    timeframe: str | None = None
    strategy: str | None = None
    score: float | None = None
    detail: str = ""


class UsageStat(BaseModel):
    metric: str
    value: float | int


class SiteConfig(BaseModel):
    """Editable site-level defaults owned by the operator (solo SaaS)."""
    default_timeframe: str = "1h"
    default_symbol: str = "BTC/USDT"
    default_source: str = "test"
    default_initial_capital: float = 100_000.0
    default_commission: float = 0.001
    default_slippage: float = 0.0005
    max_position_pct: float = 1.0
    risk_guard_daily_loss_pct: float = 0.0   # 0 = disabled
    risk_guard_max_drawdown_pct: float = 0.0  # 0 = disabled
    maintenance_mode: bool = False
    llm_model: str = "novita/tencent-hy3"  # 預設 LLM 模型 (agent_loop)
    updated_at: str = ""

    model_config = {"extra": "forbid"}


class SiteConfigUpdate(BaseModel):
    """Partial update — only provided fields are changed."""
    default_timeframe: str | None = None
    default_symbol: str | None = None
    default_source: str | None = None
    default_initial_capital: float | None = None
    default_commission: float | None = None
    default_slippage: float | None = None
    max_position_pct: float | None = None
    risk_guard_daily_loss_pct: float | None = None
    risk_guard_max_drawdown_pct: float | None = None
    maintenance_mode: bool | None = None
    llm_model: str | None = None

    model_config = {"extra": "forbid"}