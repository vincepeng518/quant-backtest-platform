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
from data.providers.tradfi import TradFiProvider
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
        self.tradfi = TradFiProvider()
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

        # 自动识别 TradFi 符号 (yfinance/Yahoo ticker)，即使 route 未传 source 也走 Yahoo
        if source != "csv" and source != "test" and self._is_tradfi(symbol):
            source = "tradfi"

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
        elif source == "tradfi":
            data = await self._try_fetch(self.tradfi, symbol, timeframe, start_date, end_date)
        elif source == "binance":
            data = await self._try_fetch(self.binance, symbol, timeframe, start_date, end_date)
        else:  # default: bingx
            # BingX 商品/贵金属合约对 (NCCO*/PAXG/XAUT) 需 -USDT 格式供 ccxt
            fetch_sym = symbol
            if symbol.upper().startswith("NCCO") or symbol.upper() in {"PAXG/USDT", "XAUT/USDT"}:
                fetch_sym = symbol.replace("/USDT", "-USDT")
            data = await self._try_fetch(self.bingx, fetch_sym, timeframe, start_date, end_date)
            # Fallback chain: bingx -> binance -> csv
            if data is None or len(data) == 0:
                data = await self._try_fetch(self.binance, symbol, timeframe, start_date, end_date)
            if data is None or len(data) == 0:
                logger.info("Falling back to CSV for %s", symbol)
                data = self.csv_loader.load(symbol)
        return data if data is not None else pd.DataFrame()

    @staticmethod
    def _is_tradfi(symbol: str) -> bool:
        s = symbol.upper()
        # BingX 商品/贵金属合约对 (NCCO*/PAXG/XAUT) 走 BingX, 不算 Yahoo tradfi
        if s.startswith("NCCO") or s in {"PAXG-USDT", "XAUT-USDT"}:
            return False
        # Yahoo ticker 特征: 含 = (外汇/指数如 EURUSD=X), 或 -USD, 或纯字母股票/ETF
        if "=" in s or s.endswith("-USD") or s in {
            "AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "META", "GOOGL",
            "SPY", "QQQ", "DIA", "GC=F", "SI=F", "CL=F", "BTC-USD",
        }:
            return True
        # 纯大写字母且无 / (非 BTC/USDT 这种 crypto 对)
        if "/" not in s and s.replace("=", "").replace("-", "").isalpha() and len(s) <= 5:
            return True
        return False

    async def _try_fetch(self, provider, symbol, timeframe, start_date, end_date) -> pd.DataFrame | None:
        try:
            return await provider.fetch_ohlcv(symbol, timeframe, start_date, end_date)
        except Exception as e:
            logger.warning("%s fetch failed for %s: %s", type(provider).__name__, symbol, e)
            return None

    async def get_symbols(self) -> list[dict]:
        # 动态拉取 BingX 全量 USDT 活跃交易对 (支持全币種 + 搜索)
        cached = cache.get("symbols:all")
        if cached and isinstance(cached, dict) and "symbols" in cached:
            return cached["symbols"]  # type: ignore[return-value]

        crypto_syms = await self._crypto_symbols()

        # TradFi 精选列表 (yfinance 不支持 load_markets 全量枚举)
        tradfi_syms = [
            {"symbol": "AAPL", "market": "tradfi", "exchange": "nasdaq", "name": "Apple"},
            {"symbol": "TSLA", "market": "tradfi", "exchange": "nasdaq", "name": "Tesla"},
            {"symbol": "NVDA", "market": "tradfi", "exchange": "nasdaq", "name": "NVIDIA"},
            {"symbol": "MSFT", "market": "tradfi", "exchange": "nasdaq", "name": "Microsoft"},
            {"symbol": "AMZN", "market": "tradfi", "exchange": "nasdaq", "name": "Amazon"},
            {"symbol": "META", "market": "tradfi", "exchange": "nasdaq", "name": "Meta"},
            {"symbol": "GOOGL", "market": "tradfi", "exchange": "nasdaq", "name": "Alphabet"},
            {"symbol": "SPY", "market": "tradfi", "exchange": "nyse", "name": "S&P 500 ETF"},
            {"symbol": "QQQ", "market": "tradfi", "exchange": "nasdaq", "name": "Nasdaq 100 ETF"},
            {"symbol": "DIA", "market": "tradfi", "exchange": "nyse", "name": "Dow Jones ETF"},
            {"symbol": "EURUSD=X", "market": "tradfi", "exchange": "fx", "name": "EUR/USD"},
            {"symbol": "USDJPY=X", "market": "tradfi", "exchange": "fx", "name": "USD/JPY"},
            {"symbol": "GC=F", "market": "tradfi", "exchange": "comex", "name": "黄金 Gold"},
            {"symbol": "SI=F", "market": "tradfi", "exchange": "comex", "name": "白银 Silver"},
            {"symbol": "CL=F", "market": "tradfi", "exchange": "nymex", "name": "原油 WTI"},
            {"symbol": "BTC-USD", "market": "tradfi", "exchange": "crypto", "name": "Bitcoin (Yahoo)"},
        ]

        result = crypto_syms + tradfi_syms
        cache.set("symbols:all", {"symbols": result}, ttl=3600)
        return result

    async def _crypto_symbols(self) -> list[dict]:
        # BingX 商品/贵金属合约对 (NCCO* = Non-Crypto Commodity)，UI 归 TradFi 板块
        # 但数据仍走 BingX (不是 Yahoo XAU)，保留原生 symbol 格式
        COMMODITY_MAP = {
            "NCCOXAG2USD-USDT": "白银 Silver",
            "NCCOXPT2USD-USDT": "铂金 Platinum",
            "NCCOPALLADIUM2USD-USDT": "钯金 Palladium",
            "NCCO724COPPER2USD-USDT": "铜 Copper",
            "NCCONICKEL2USD-USDT": "镍 Nickel",
            "NCCOZINC2USD-USDT": "锌 Zinc",
            "NCCOALUMINIUM2USD-USDT": "铝 Aluminium",
            "NCCOLEAD2USD-USDT": "铅 Lead",
            "NCCO1OILBRENT2USD-USDT": "布伦特原油 Brent",
            "NCCO1OILWTI2USD-USDT": "WTI原油 Crude Oil",
            "NCCOHEATINGOIL2USD-USDT": "取暖油 Heating Oil",
            "NCCOGASOLINE2USD-USDT": "汽油 Gasoline",
            "NCCO7241NATGAS2USD-USDT": "天然气 Natural Gas",
            "NCCOGOLD2USD-USDT": "黄金综合 Gold",
            "NCCOXAUAUD2USD-USDT": "黄金(澳元) Gold/AUD",
            "NCCOWHEAT2USD-USDT": "小麦 Wheat",
            "NCCOSOYBEANS2USD-USDT": "大豆 Soybeans",
            "NCCOCOTTON2USD-USDT": "棉花 Cotton",
            "NCFXAUD2USD-USDT": "澳元/美元 AUD/USD",
            "PAXG-USDT": "Paxos Gold",
            "XAUT-USDT": "Tether Gold",
        }
        COMMODITY_SET = set(COMMODITY_MAP.keys())

        try:
            import ccxt

            ex = ccxt.bingx()
            ex.timeout = 20_000
            markets = await asyncio.to_thread(ex.load_markets)
            usdt = sorted(
                k for k, m in markets.items()
                if (k.endswith("/USDT") or k.endswith("-USDT"))
                and m.get("active", True) is not False  # BingX active 常为 None
            )
            # ccxt 用 /USDT, BingX 原生用 -USDT；统一转 /USDT 供上层使用
            usdt = [k.replace("-USDT", "/USDT") if k.endswith("-USDT") else k for k in usdt]
        except Exception as e:
            logger.warning("load_markets failed: %s — fallback to static list", e)
            usdt = ["BTC/USDT", "ETH/USDT", "SOL/USDT"] + list(COMMODITY_SET)

        pinned = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
                  "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "TON/USDT",
                  "MATIC/USDT", "TRX/USDT", "DOT/USDT", "NEAR/USDT", "LTC/USDT"]
        ordered = [s for s in pinned if s in usdt] + [s for s in usdt if s not in pinned]

        out = []
        for s in ordered:
            # BingX 合约对格式 NCCO...-USDT → ccxt 用 NCCO.../USDT
            bingx_sym = s.replace("/", "-") if "/" in s else s
            if bingx_sym in COMMODITY_SET:
                out.append({
                    "symbol": s, "market": "tradfi", "exchange": "bingx",
                    "description": COMMODITY_MAP[bingx_sym],
                })
            else:
                out.append({"symbol": s, "market": "crypto", "exchange": "bingx"})

        # 兜底: load_markets 未返回 NCCO 商品对时, 直接注入已知列表 (BingX 商品对固定小集合)
        existing = {x["symbol"] for x in out}
        for bingx_sym, name in COMMODITY_MAP.items():
            sym = bingx_sym.replace("-USDT", "/USDT")
            if sym not in existing:
                out.append({"symbol": sym, "market": "tradfi", "exchange": "bingx", "description": name})
        return out


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