from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import yaml


@dataclass
class MonitorConfig:
    binance_symbol: str = "btcusdt@trade"
    target_source: str = "none"
    dev_base_points: float = 25.0
    dev_min_points: float = 15.0
    dev_max_points: float = 80.0
    dev_vol_mult: float = 1.5
    dev_window: int = 60
    min_secs_to_close: int = 150
    max_secs_to_close: int = 200
    odds_min: float = 0.60
    odds_max: float = 0.75
    min_depth_shares: float = 1000.0
    anomaly_vol_mult: float = 4.0
    anomaly_lookback: int = 30
    ob_source: str = "polymarket"
    ob_token_id: str = ""
    ob_refresh_sec: float = 2.0
    api_key: str = ""            # predict.fun API Key (REST 真值源: startPrice/endPrice)
    db: str = "monitoring/shadow.db"
    log: str = "monitoring/monitor.log"
    settle_on_close: bool = True
    tail_min: int = 10
    tail_max: int = 20

    @classmethod
    def load(cls, path: str = "monitoring/config.yaml") -> "MonitorConfig":
        if not os.path.exists(path):
            return cls()
        with open(path) as f:
            d = yaml.safe_load(f) or {}
        feed = d.get("feed", {})
        dev = d.get("deviation", {})
        tim = d.get("timing", {})
        odds = d.get("odds", {})
        depth = d.get("depth", {})
        anom = d.get("anomaly", {})
        ob = d.get("orderbook", {})
        sto = d.get("storage", {})
        run = d.get("run", {})
        return cls(
            binance_symbol=feed.get("binance_symbol", cls.binance_symbol),
            target_source=feed.get("target_source", cls.target_source),
            dev_base_points=dev.get("base_points", cls.dev_base_points),
            dev_min_points=dev.get("min_points", cls.dev_min_points),
            dev_max_points=dev.get("max_points", cls.dev_max_points),
            dev_vol_mult=dev.get("vol_mult", cls.dev_vol_mult),
            dev_window=dev.get("window", cls.dev_window),
            min_secs_to_close=tim.get("min_secs_to_close", cls.min_secs_to_close),
            max_secs_to_close=tim.get("max_secs_to_close", cls.max_secs_to_close),
            odds_min=odds.get("min", cls.odds_min),
            odds_max=odds.get("max", cls.odds_max),
            min_depth_shares=depth.get("min_shares", cls.min_depth_shares),
            anomaly_vol_mult=anom.get("vol_mult", cls.anomaly_vol_mult),
            anomaly_lookback=anom.get("lookback", cls.anomaly_lookback),
            ob_source=ob.get("source", cls.ob_source),
            ob_token_id=ob.get("polymarket_token_id", cls.ob_token_id),
            ob_refresh_sec=ob.get("book_refresh_sec", cls.ob_refresh_sec),
            api_key=ob.get("api_key", cls.api_key),
            db=sto.get("db", cls.db),
            log=sto.get("log", cls.log),
            settle_on_close=run.get("settle_on_close", cls.settle_on_close),
            tail_min=run.get("tail_snapshot_secs", [10, 20])[0],
            tail_max=run.get("tail_snapshot_secs", [10, 20])[1],
        )
