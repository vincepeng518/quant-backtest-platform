"""
app/services/portfolio_service.py — 多標的組合對沖回測 service。

只新增組合計算模組,不碰單標的回測路徑(單標 Backtester 原樣使用)。
流程: 對組合內每標的 → 取 ohlcv → 各跑指定策略(單標引擎) → 得 equity+timestamps
     → 時間對齊 → engine.portfolio.run_portfolio(日回報空間加權組合 + 相關性矩陣 + 對沖報告)。

異常負值防護: portfolio.run_portfolio 若 errors 有值(非有限/NaN/負權重),原樣帶回給前端,不吞。
"""
from __future__ import annotations
import math
import logging
from typing import Any, Dict, List

import pandas as pd

from engine.backtester import Backtester
from engine.portfolio import run_portfolio, PortfolioResult
from app.services.data_service import DataService
from app.services.strategy_service import get_strategy

logger = logging.getLogger(__name__)


def _resolve_source(symbol: str, source: str) -> str:
    if not source or source == "binance":
        if symbol.upper().startswith(("NCCO", "NCFX", "NCSI", "NCSK")):
            return "bingx_tradfi"
        return "bingx"
    return source


async def _run_single(
    ds: DataService,
    symbol: str,
    source: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    strategy_cls,
    strategy_params: dict,
    initial_capital: float,
    commission: float,
) -> Dict[str, Any]:
    """對單一標的跑單標回測,回傳該標的 equity_curve + timestamps(epoch ms)。"""
    src = _resolve_source(symbol, source)
    data = await ds.get_ohlcv(symbol=symbol, timeframe=timeframe,
                              start_date=start_date, end_date=end_date, source=src)
    if data is None or len(data) == 0:
        raise ValueError(f"{symbol}: 無資料(No data)")
    # timestamp 統一 epoch ms
    ts_col = data["timestamp"]
    if len(ts_col) > 0 and isinstance(ts_col.iloc[0], (int, float)) and ts_col.iloc[0] > 1e11:
        ts_ms = pd.to_datetime(ts_col, unit="ms", errors="coerce")
    elif len(ts_col) > 0 and isinstance(ts_col.iloc[0], (int, float)):
        ts_ms = pd.to_datetime(ts_col, unit="s", errors="coerce")
    else:
        ts_ms = pd.to_datetime(ts_col, errors="coerce")
    timestamps = [int(t) if not pd.isna(t) else 0 for t in ts_ms.astype("int64") // 10**6]

    bt = Backtester(initial_capital=initial_capital, commission=commission, slippage=0.0005)
    bt.set_data(data)
    strategy = strategy_cls()
    strategy.init(strategy_params or {})
    bt.set_strategy(strategy)
    res = bt.run()
    equity = list(getattr(res, "equity_curve", [])) or []
    if not equity or not math.isfinite(equity[-1]):
        raise ValueError(f"{symbol}: 回測 equity 異常(空或非有限)— 卡關回報")
    # equity 與 timestamps 可能不等長(data 開頭有 NaN 期), 截斷到等長
    n = min(len(equity), len(timestamps))
    return {"symbol": symbol, "equity": equity[:n], "timestamps": timestamps[:n], "metrics": {
        "sharpe": getattr(res, "sharpe_ratio", 0), "total_pnl": getattr(res, "total_pnl", 0),
        "total_return_pct": getattr(res, "total_return_pct", 0), "win_rate": getattr(res, "win_rate", 0),
        "max_drawdown_pct": getattr(res, "max_drawdown_pct", 0), "trades": getattr(res, "total_trades", 0),
    }}


async def run_portfolio_backtest(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    config: {
      symbols: [..], strategy: {template_id, params}, timeframe, start_date, end_date,
      initial_capital, commission, source, weights: {sym: w}
    }
    回傳含 correlation_matrix / portfolio_metrics / hedge_report / individual_metrics / portfolio_equity。
    任何標的失敗或組合異常 → 回傳 { status:"error", error } 帶詳細。
    """
    symbols: List[str] = config.get("symbols") or []
    if len(symbols) < 2:
        return {"status": "error", "error": "組合至少需 2 個標的"}
    strat_cfg = config.get("strategy") or {}
    template_id = strat_cfg.get("template_id", "ma_cross")
    try:
        strategy_cls = get_strategy(template_id)
    except KeyError as e:
        return {"status": "error", "error": str(e)}

    ds = DataService()
    timeframe = config.get("timeframe", "1h")
    start_date = config.get("start_date", "")
    end_date = config.get("end_date", "")
    initial_capital = float(config.get("initial_capital", 100_000))
    commission = float(config.get("commission", 0.001))
    weights = config.get("weights") or None

    # 並行跑各標的單標回測(不相依,平行)
    import asyncio
    results = await asyncio.gather(
        *[_run_single(ds, s, config.get("source", ""), timeframe, start_date, end_date,
                      strategy_cls, strat_cfg.get("params") or {}, initial_capital, commission)
          for s in symbols],
        return_exceptions=True,
    )
    equity_map: Dict[str, list] = {}
    ts_map: Dict[str, list] = {}
    ind_metrics: Dict[str, dict] = {}
    errors: List[str] = []
    for r, sym in zip(results, symbols):
        if isinstance(r, Exception):
            errors.append(f"{sym}: {r}")
            continue
        if not isinstance(r, dict):   # 防非預期型別
            errors.append(f"{sym}: 回測回傳非預期型別")
            continue
        equity_map[sym] = r["equity"]
        ts_map[sym] = r["timestamps"]
        ind_metrics[sym] = r["metrics"]

    if len(equity_map) < 2:
        return {"status": "error", "error": f"可用的標的不足(需≥2)。詳細: {errors}"}

    # 組合計算(相關性矩陣 + 對沖報告)
    pf: PortfolioResult = run_portfolio(
        equity_by_symbol=equity_map,
        timestamps_by_symbol=ts_map,
        weights=weights,
    )
    # ⚠️ 防護性警告(爆倉clip / 負權重) → 併入 warnings, 組合仍可用 clip 後的健康資料。
    #    只有組合完全沒算出(empty equity / 非有限)才視為致命 error。
    all_warnings = list(errors) + list(pf.errors)
    if not pf.portfolio_equity or len(pf.portfolio_equity) == 0:
        return {"status": "error", "error": f"組合計算失敗(無組合equity): {pf.errors}", "partial": {
            "individual_metrics": ind_metrics, "weights": pf.weights}}
    # 組合 equity 若有非有限 → 致命
    import math as _m
    bad = [i for i, v in enumerate(pf.portfolio_equity) if not _m.isfinite(v)]
    if bad:
        return {"status": "error", "error": f"組合計算異常負值/非有限於 index {bad[:5]}", "partial": {
            "individual_metrics": ind_metrics, "weights": pf.weights}}

    return {
        "status": "ok",
        "symbols": symbols,
        "correlation_matrix": pf.correlation_matrix,
        "weights": pf.weights,
        "individual_metrics": ind_metrics,
        "pf_individual_metrics": pf.individual_metrics,   # 風險指標(sharpe/vol) 各標的
        "portfolio_metrics": pf.portfolio_metrics,        # 組合風險(sharpe/vol/mdd)
        "hedge_report": pf.hedge_report,                  # 對沖價值(best_single_vol/負相關對/vol降幅)
        "portfolio_equity": pf.portfolio_equity,
        "portfolio_returns": pf.portfolio_returns,
        "timestamps": pf.timestamps,
        "errors": [],
        "warnings": all_warnings,   # 含爆倉clip / 負權重 / 標的失敗警告
    }
