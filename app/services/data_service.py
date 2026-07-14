from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.utils.cache import cache
from data.providers.binance import BinanceProvider
from data.providers.bingx import BingXProvider
from data.providers.csv_loader import CSVLoader

logger = logging.getLogger(__name__)

# In-memory task store (production → Redis)
_backtest_tasks: dict[str, dict] = {}
_optimize_tasks: dict[str, dict] = {}
_analysis_tasks: dict[str, dict] = {}


class DataService:
    def __init__(self) -> None:
        self.binance = BinanceProvider()
        self.bingx = BingXProvider()
        self.csv_loader = CSVLoader()

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        start_date: str = "",
        end_date: str = "",
        source: str = "bingx",
    ) -> pd.DataFrame:
        cache_key = f"ohlcv:{symbol}:{timeframe}:{start_date}:{end_date}:{source}"
        cached = cache.get(cache_key)
        if cached is not None:
            return pd.DataFrame(cached)

        data: pd.DataFrame | None = None
        if source == "csv" or source == "test":
            # local CSV only — no network (for fast testing / offline)
            data = self.csv_loader.load(symbol)
            # If disk CSV is missing or too short (e.g. stale deploy cache),
            # generate fresh in-memory test data so offline mode always works.
            if data is None or len(data) < 5000:
                from data.providers.test_data import generate_test_data

                gen = generate_test_data(symbol.replace("/", "_"))
                if gen is not None and len(gen) > 0:
                    data = gen
        elif source == "binance":
            data = await self._try_fetch(self.binance, symbol, timeframe, start_date, end_date)
        else:  # default: bingx
            data = await self._try_fetch(self.bingx, symbol, timeframe, start_date, end_date)
            # Fallback chain: bingx -> binance -> csv
            if data is None or len(data) == 0:
                data = await self._try_fetch(self.binance, symbol, timeframe, start_date, end_date)
            if data is None or len(data) == 0:
                logger.info("Falling back to CSV for %s", symbol)
                data = self.csv_loader.load(symbol)

        if data is not None and len(data):
            cache.set(cache_key, data.to_dict(orient="records"))
        return data if data is not None else pd.DataFrame()

    async def _try_fetch(self, provider, symbol, timeframe, start_date, end_date) -> pd.DataFrame | None:
        try:
            return await provider.fetch_ohlcv(symbol, timeframe, start_date, end_date)
        except Exception as e:
            logger.warning("%s fetch failed for %s: %s", type(provider).__name__, symbol, e)
            return None

    async def get_symbols(self) -> list[dict]:
        # 动态拉取 BingX 全量 USDT 活跃交易对 (支持全币種 + 搜索)
        cached = cache.get("symbols:bingx")
        if cached and isinstance(cached, dict) and "symbols" in cached:
            return cached["symbols"]  # type: ignore[return-value]

        try:
            import ccxt

            ex = ccxt.bingx()
            ex.timeout = 20_000
            markets = await asyncio.to_thread(ex.load_markets)
            usdt = sorted(
                k for k, m in markets.items()
                if k.endswith("/USDT") and m.get("active", True)
            )
        except Exception as e:
            logger.warning("load_markets failed: %s — fallback to static list", e)
            usdt = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

        # 常用币置顶，便于搜索时优先看到
        pinned = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
                  "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "TON/USDT",
                  "MATIC/USDT", "TRX/USDT", "DOT/USDT", "NEAR/USDT", "LTC/USDT"]
        ordered = [s for s in pinned if s in usdt] + [s for s in usdt if s not in pinned]

        result = [
            {"symbol": s, "market": "crypto", "exchange": "bingx"} for s in ordered
        ]
        cache.set("symbols:bingx", {"symbols": result}, ttl=3600)
        return result


def create_task_id() -> str:
    return str(uuid.uuid4())[:8]


async def _execute_backtest(task_id: str, backtester, store: dict[str, dict]) -> None:
    try:
        result = backtester.run()
        store[task_id]["status"] = "completed"
        store[task_id]["result"] = result

        # P3: persist result to git for history (survives restart)
        try:
            from app.services.strategy_git import git_persist
            bd = Path(__file__).resolve().parents[2] / "backtests"
            bd.mkdir(parents=True, exist_ok=True)
            cfg = store[task_id].get("config", {})
            payload = {
                "task_id": task_id,
                "status": "completed",
                "created_at": datetime.utcnow().isoformat(),
                "config": cfg,
                "metrics": asdict(result),
                "equity_curve": result.equity_curve,
                "trades": [asdict(t) for t in result.trades],
            }
            fp = bd / f"{task_id}.json"
            fp.write_text(json.dumps(payload, default=str, indent=2))
            ok, detail = git_persist([str(fp)], f"feat(backtest): save {task_id}")
            if not ok:
                logger.warning("backtest persist skipped: %s", detail)
        except Exception as _e:
            logger.warning("backtest persist failed: %s", _e)
    except Exception as e:
        logger.exception("Backtest failed")
        store[task_id]["status"] = "error"
        store[task_id]["error"] = str(e)


def get_task(task_id: str, store: dict) -> Optional[dict]:
    return store.get(task_id)