from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_KLINES_URL = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"

# 你提供的完整 BingX TradFi 標的清單。status 由 probe_symbols() 實測更新。
#  - active   : 當前可抓 K 線 (實測 OK)
#  - paused   : BingX 回傳 "is pause currently"
#  - offline  : BingX 回傳 "is offline currently"
#  - not_exist: BingX 回傳 "not exist"
# 初始狀態為 2026-07-18 實測結果，探活後自動刷新。
BINGX_TRADFI_SYMBOLS: list[dict] = [
    # ── FX majors ──
    {"symbol": "NCFXEUR2USD-USDT", "category": "fx", "name": "EUR/USD", "status": "paused"},
    {"symbol": "NCFXGBP2USD-USDT", "category": "fx", "name": "GBP/USD", "status": "paused"},
    {"symbol": "NCFXUSD2JPY-USDT", "category": "fx", "name": "USD/JPY", "status": "paused"},
    {"symbol": "NCFXAUD2USD-USDT", "category": "fx", "name": "AUD/USD", "status": "paused"},
    {"symbol": "NCFXUSD2CAD-USDT", "category": "fx", "name": "USD/CAD", "status": "paused"},
    {"symbol": "NCFXUSD2CHF-USDT", "category": "fx", "name": "USD/CHF", "status": "paused"},
    # ── crosses & others ──
    {"symbol": "NCFXGBP2JPY-USDT", "category": "fx", "name": "GBP/JPY", "status": "paused"},
    {"symbol": "NCFXEUR2JPY-USDT", "category": "fx", "name": "EUR/JPY", "status": "paused"},
    {"symbol": "NCFXNZD2USD-USDT", "category": "fx", "name": "NZD/USD", "status": "paused"},
    {"symbol": "NCFXEUR2CAD-USDT", "category": "fx", "name": "EUR/CAD", "status": "paused"},
    {"symbol": "NCFXEUR2GBP-USDT", "category": "fx", "name": "EUR/GBP", "status": "paused"},
    {"symbol": "NCFXEUR2CHF-USDT", "category": "fx", "name": "EUR/CHF", "status": "paused"},
    {"symbol": "NCFXGBP2CHF-USDT", "category": "fx", "name": "GBP/CHF", "status": "paused"},
    {"symbol": "NCFXAUD2JPY-USDT", "category": "fx", "name": "AUD/JPY", "status": "paused"},
    # ── EM ──
    {"symbol": "NCFXUSDSGD2USD-USDT", "category": "fx", "name": "USD/SGD", "status": "paused"},
    {"symbol": "NCFXEURSGD2USD-USDT", "category": "fx", "name": "EUR/SGD", "status": "paused"},
    {"symbol": "NCFXGBPSGD2USD-USDT", "category": "fx", "name": "GBP/SGD", "status": "paused"},
    {"symbol": "NCFXUSDBRL2USD-USDT", "category": "fx", "name": "USD/BRL", "status": "paused"},
    # ── metals ──
    {"symbol": "NCCOGOLD2USD-USDT", "category": "metal", "name": "Gold", "status": "active"},
    {"symbol": "NCCOSILVER2USD-USDT", "category": "metal", "name": "Silver", "status": "offline"},
    {"symbol": "NCCOPALLADIUM2USD-USDT", "category": "metal", "name": "Palladium", "status": "active"},
    {"symbol": "NCCOCOPPER2USD-USDT", "category": "metal", "name": "Copper (LME)", "status": "offline"},
    {"symbol": "NCCONICKEL2USD-USDT", "category": "metal", "name": "Nickel", "status": "paused"},
    {"symbol": "NCCOZINC2USD-USDT", "category": "metal", "name": "Zinc", "status": "paused"},
    {"symbol": "NCCOALUMINUM2USD-USDT", "category": "metal", "name": "Aluminium", "status": "paused"},
    {"symbol": "NCCOLEAD2USD-USDT", "category": "metal", "name": "Lead", "status": "paused"},
    {"symbol": "NCCOCOFFEE2USD-USDT", "category": "metal", "name": "Coffee", "status": "paused"},
    # ── energy ──
    {"symbol": "NCCOOILBRENT2USD-USDT", "category": "energy", "name": "Brent Crude", "status": "offline"},
    {"symbol": "NCCOOILWTI2USD-USDT", "category": "energy", "name": "WTI Crude", "status": "offline"},
    {"symbol": "NCCONATURALGAS2USD-USDT", "category": "energy", "name": "Natural Gas", "status": "offline"},
    {"symbol": "NCCOGASOLINE2USD-USDT", "category": "energy", "name": "Gasoline", "status": "paused"},
    {"symbol": "NCCOHEATINGOIL2USD-USDT", "category": "energy", "name": "Heating Oil", "status": "paused"},
    {"symbol": "NCCOCOCOA2USD-USDT", "category": "energy", "name": "Cocoa", "status": "paused"},
    {"symbol": "NCCOSOYBEANS2USD-USDT", "category": "energy", "name": "Soybeans", "status": "paused"},
    # ── indices US ──
    {"symbol": "NCSINASDAQ1002USD-USDT", "category": "index", "name": "Nasdaq 100", "status": "active"},
    {"symbol": "NCSISP5002USD-USDT", "category": "index", "name": "S&P 500", "status": "active"},
    {"symbol": "NCSIDOWJONES2USD-USDT", "category": "index", "name": "Dow Jones IA", "status": "paused"},
    {"symbol": "NCSIRUSSELL20002USD-USDT", "category": "index", "name": "Russell 2000", "status": "paused"},
    # ── asia ──
    {"symbol": "NCSINIKKEI2252USD-USDT", "category": "index", "name": "Nikkei 225", "status": "paused"},
    # ── stocks ──
    {"symbol": "NCSKAAPL2USD-USDT", "category": "stock", "name": "Apple", "status": "active"},
    {"symbol": "NCSKMSFT2USD-USDT", "category": "stock", "name": "Microsoft", "status": "active"},
    {"symbol": "NCSKGOOGL2USD-USDT", "category": "stock", "name": "Alphabet", "status": "active"},
    {"symbol": "NCSKAMZN2USD-USDT", "category": "stock", "name": "Amazon", "status": "active"},
    {"symbol": "NCSKTSLA2USD-USDT", "category": "stock", "name": "Tesla", "status": "active"},
    {"symbol": "NCSKMETA2USD-USDT", "category": "stock", "name": "Meta", "status": "active"},
    {"symbol": "NCSKNVDA2USD-USDT", "category": "stock", "name": "NVIDIA", "status": "active"},
    {"symbol": "NCSKARM2USD-USDT", "category": "stock", "name": "ARM", "status": "active"},
    {"symbol": "NCSKCOIN2USD-USDT", "category": "stock", "name": "Coinbase", "status": "active"},
    {"symbol": "NCSKMSTR2USD-USDT", "category": "stock", "name": "MicroStrategy", "status": "active"},
    {"symbol": "NCSKHOOD2USD-USDT", "category": "stock", "name": "Robinhood", "status": "active"},
    {"symbol": "NCSKPLTR2USD-USDT", "category": "stock", "name": "Palantir", "status": "active"},
    {"symbol": "NCSKRDDT2USD-USDT", "category": "stock", "name": "Reddit", "status": "active"},
    {"symbol": "NCSKINTC2USD-USDT", "category": "stock", "name": "Intel", "status": "active"},
    {"symbol": "NCSKCSCO2USD-USDT", "category": "stock", "name": "Cisco", "status": "offline"},
    {"symbol": "NCSKACN2USD-USDT", "category": "stock", "name": "Accenture", "status": "offline"},
    {"symbol": "NCSKASML2USD-USDT", "category": "stock", "name": "ASML", "status": "active"},
    {"symbol": "NCSKORCL2USD-USDT", "category": "stock", "name": "Oracle", "status": "active"},
    {"symbol": "NCSKIBM2USD-USDT", "category": "stock", "name": "IBM", "status": "offline"},
    {"symbol": "NCSKMRVL2USD-USDT", "category": "stock", "name": "Marvell", "status": "active"},
    {"symbol": "NCSKAPP2USD-USDT", "category": "stock", "name": "AppLovin", "status": "active"},
    {"symbol": "NCSKCRCL2USD-USDT", "category": "stock", "name": "Circle", "status": "active"},
    {"symbol": "NCSKMCD2USD-USDT", "category": "stock", "name": "McDonald's", "status": "active"},
    {"symbol": "NCSKGE2USD-USDT", "category": "stock", "name": "GE", "status": "active"},
    {"symbol": "NCSKGME2USD-USDT", "category": "stock", "name": "GameStop", "status": "active"},
]

TF_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}


def active_symbols() -> list[str]:
    return [s["symbol"] for s in BINGX_TRADFI_SYMBOLS if s["status"] == "active"]


class BingXTradFiProvider:
    """OHLCV provider for BingX TradFi (NCCO/NCFX/NCSI/NCSK) contracts via openApi klines.

    Unlike BingXProvider (ccxt), these contracts are not always ccxt-visible, so we
    hit the public openApi REST endpoint directly. Supports multi-page history fetch
    and [start_date, end_date] filtering.
    """

    def __init__(self, symbols: Optional[list[dict]] = None) -> None:
        self.symbols = symbols if symbols is not None else BINGX_TRADFI_SYMBOLS

    def _fetch_page(self, symbol: str, interval: str, start_ms: Optional[int], limit: int) -> list[list]:
        params = {"symbol": symbol, "interval": interval, "limit": min(limit, 1000)}
        if start_ms is not None:
            params["startTime"] = start_ms
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{_KLINES_URL}?{qs}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())  # noqa: F821
        if d.get("code") != 0:
            raise RuntimeError(f"BingX klines error {d.get('code')}: {d.get('msg')}")
        return d.get("data", [])

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        start_date: str = "",
        end_date: str = "",
        limit: int = 1000,
    ) -> Optional[pd.DataFrame]:
        try:
            import json as _json  # local ref for closure above
            tf_ms = TF_MS.get(timeframe, 3_600_000)
            start_ms = None
            if start_date:
                start_ms = int(pd.Timestamp(start_date).timestamp() * 1000)
            end_ms = None
            if end_date:
                end_ms = int(pd.Timestamp(end_date).timestamp() * 1000)

            frames: list[list] = []
            cursor = start_ms
            remaining = limit
            max_pages = 12
            for _ in range(max_pages):
                if remaining <= 0:
                    break
                raw = await asyncio.to_thread(
                    self._fetch_page, symbol, timeframe, cursor, min(remaining, 1000)
                )
                if not raw:
                    break
                frames.append(raw)
                remaining -= len(raw)
                last_ts = int(raw[-1]["time"])
                if end_ms is not None and last_ts >= end_ms:
                    break
                cursor = last_ts + tf_ms
                if cursor <= 0:
                    break

            if not frames:
                return None

            import itertools
            merged = list(itertools.chain.from_iterable(frames))
            df = pd.DataFrame(merged)
            df["timestamp"] = pd.to_datetime(pd.to_numeric(df["time"]), unit="ms")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            df = df[["timestamp", "open", "high", "low", "close", "volume"]]
            df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
            if start_ms is not None:
                df = df[df["timestamp"] >= pd.to_datetime(start_ms, unit="ms")]
            if end_ms is not None:
                df = df[df["timestamp"] <= pd.to_datetime(end_ms, unit="ms")]
            return df.reset_index(drop=True) if len(df) else None
        except Exception as e:
            logger.warning("BingXTradFi fetch failed for %s: %s", symbol, e)
            return None

    async def probe_symbols(self) -> list[dict]:
        """Re-probe every symbol and update in-place status. Returns the updated list."""
        import concurrent.futures

        def _probe(sym: str) -> str:
            url = f"{_KLINES_URL}?symbol={sym}&interval=1d&limit=1"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    d = json.loads(r.read())
                if d.get("code") == 0 and d.get("data"):
                    return "active"
                msg = (d.get("msg") or "").lower()
                if "offline" in msg:
                    return "offline"
                if "pause" in msg:
                    return "paused"
                return "not_exist"
            except Exception:
                return "not_exist"

        syms = [s["symbol"] for s in self.symbols]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(_probe, syms))
        for s, st in zip(self.symbols, results):
            s["status"] = st
        return self.symbols
