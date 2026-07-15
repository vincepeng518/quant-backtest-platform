from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.schemas import (
    CredentialStatus,
    MonitoredSymbol,
    TaskHistoryItem,
    UsageStat,
    SiteConfig,
    SiteConfigUpdate,
)

# Repo-relative data dir (same area as backtest.db). Overridable via DATA_DIR.
_DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data")))

# Backtests are persisted here by app/services/data_service.py (_execute_backtest).
_BACKTESTS_DIR = Path(os.getenv("BACKTESTS_DIR", str(Path(__file__).resolve().parents[2] / "backtests")))

# Environment variables we treat as operator credentials. Values are NEVER returned
# in plaintext — only a masked preview + configured flag.
_CREDENTIAL_ENV = [
    ("BINANCE_API_KEY", "exchange", "Binance API Key"),
    ("BINANCE_API_SECRET", "exchange", "Binance API Secret"),
    ("BINGX_API_KEY", "exchange", "BingX API Key"),
    ("BINGX_API_SECRET", "exchange", "BingX API Secret"),
    ("REDIS_URL", "infra", "Redis connection"),
    ("MONITOR_PUSH_KEY", "infra", "Monitoring push key"),
    ("OPENAI_API_KEY", "infra", "OpenAI API Key"),
    ("NEXT_PUBLIC_API_URL", "infra", "Frontend API URL"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mask(value: str) -> str:
    """Return a safe preview of a secret without leaking it."""
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}****{value[-2:]}"


class AdminService:
    """Operator/owner panel data layer.

    Follows the same service pattern as DataService/BacktestService: a thin
    class instantiated once per router, reading/writing small JSON files under
    the repo data dir plus the pre-existing persisted backtests. No new
    framework, no new storage engine.
    """

    def __init__(self) -> None:
        self.data_dir = _DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.watchlist_path = self.data_dir / "watchlist.json"
        self.config_path = self.data_dir / "site_config.json"

    # ───────────────────────── 监控标的清单 ─────────────────────────

    def get_watchlist(self) -> list[MonitoredSymbol]:
        raw = self._read_json(self.watchlist_path, default=[])
        out: list[MonitoredSymbol] = []
        for item in raw:
            try:
                out.append(MonitoredSymbol(**item))
            except Exception:
                continue
        # pinned first, then by added_at
        out.sort(key=lambda s: (not s.pinned, s.added_at))
        return out

    def add_symbol(
        self,
        symbol: str,
        market: str = "crypto",
        exchange: str = "",
        description: str = "",
        pinned: bool = False,
    ) -> MonitoredSymbol:
        symbol = (symbol or "").strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        items = self._read_json(self.watchlist_path, default=[])
        existing = {it.get("symbol") for it in items}
        if symbol in existing:
            raise ValueError(f"{symbol} already in watchlist")
        rec = MonitoredSymbol(
            symbol=symbol,
            market=market,
            exchange=exchange,
            description=description,
            pinned=pinned,
            added_at=_now(),
        )
        items.append(rec.model_dump())
        self._write_json(self.watchlist_path, items)
        return rec

    def remove_symbol(self, symbol: str) -> bool:
        items = self._read_json(self.watchlist_path, default=[])
        before = len(items)
        items = [it for it in items if (it.get("symbol") or "").upper() != symbol.upper()]
        if len(items) == before:
            return False
        self._write_json(self.watchlist_path, items)
        return True

    def toggle_pin(self, symbol: str) -> bool:
        items = self._read_json(self.watchlist_path, default=[])
        found = False
        for it in items:
            if (it.get("symbol") or "").upper() == symbol.upper():
                it["pinned"] = not bool(it.get("pinned", False))
                found = True
                break
        if not found:
            return False
        self._write_json(self.watchlist_path, items)
        return True

    # ───────────────────────── 凭证状态（不暴露明文） ─────────────────────────

    def get_credentials(self) -> list[CredentialStatus]:
        out: list[CredentialStatus] = []
        for env_name, kind, label in _CREDENTIAL_ENV:
            raw = os.getenv(env_name, "")
            configured = bool(raw)
            out.append(
                CredentialStatus(
                    name=label,
                    kind=kind,
                    configured=configured,
                    masked_value=_mask(raw) if configured else "",
                    updated_at=None,
                )
            )
        return out

    # ───────────────────────── 任务历史（回测/优化/分析） ─────────────────────────

    def _task_kind_from_dir(self, fp: Path) -> str:
        name = fp.name.lower()
        if "optimize" in name or fp.parent.name == "optimize":
            return "optimize"
        return "backtest"

    def get_task_history(self, limit: int = 200) -> list[TaskHistoryItem]:
        items: list[TaskHistoryItem] = []
        bd = _BACKTESTS_DIR
        if bd.exists():
            files = sorted(bd.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            for fp in files[:limit]:
                try:
                    d = json.loads(fp.read_text())
                except Exception:
                    continue
                m = d.get("metrics", {}) or {}
                cfg = d.get("config", {}) or {}
                strat = cfg.get("strategy_id")
                if not strat and isinstance(cfg.get("strategy"), dict):
                    strat = cfg["strategy"].get("template_id")
                sr = m.get("sharpe_ratio")
                score = float(sr) if isinstance(sr, (int, float)) else None
                items.append(
                    TaskHistoryItem(
                        task_id=d.get("task_id", fp.stem),
                        kind="backtest",
                        status=d.get("status", "completed"),
                        created_at=d.get("created_at", ""),
                        symbol=cfg.get("symbol"),
                        timeframe=cfg.get("timeframe"),
                        strategy=strat,
                        score=score,
                        detail=cfg.get("symbol", ""),
                    )
                )
        items.sort(key=lambda x: x.created_at or "", reverse=True)
        return items[:limit]

    # ───────────────────────── 使用量统计 ─────────────────────────

    def get_usage(self) -> list[UsageStat]:
        total_backtests = 0
        completed = 0
        failed = 0
        total_trades = 0
        symbols_set: set[str] = set()
        bd = _BACKTESTS_DIR
        if bd.exists():
            for fp in bd.glob("*.json"):
                try:
                    d = json.loads(fp.read_text())
                except Exception:
                    continue
                total_backtests += 1
                st = d.get("status")
                if st == "completed":
                    completed += 1
                elif st == "error":
                    failed += 1
                m = d.get("metrics", {}) or {}
                total_trades += int(m.get("total_trades", 0) or 0)
                sym = (d.get("config", {}) or {}).get("symbol")
                if sym:
                    symbols_set.add(sym)

        # Monitoring stats (if pushed via /api/monitoring/push)
        shadow_total = 0
        try:
            _db = os.getenv("DB_PATH", "./data/backtest.db")
            c = sqlite3.connect(_db)
            try:
                row = c.execute(
                    "SELECT payload FROM monitoring_stats WHERE id=1"
                ).fetchone()
                if row:
                    payload = json.loads(row[0])
                    shadow_total = int(
                        (payload.get("shadow", {}) or {}).get("total", 0) or 0
                    )
            finally:
                c.close()
        except Exception:
            pass

        return [
            UsageStat(metric="total_runs", value=total_backtests),
            UsageStat(metric="completed_runs", value=completed),
            UsageStat(metric="failed_runs", value=failed),
            UsageStat(metric="total_trades", value=total_trades),
            UsageStat(metric="unique_symbols", value=len(symbols_set)),
            UsageStat(metric="monitor_signals", value=shadow_total),
        ]

    # ───────────────────────── 站点配置 ─────────────────────────

    def get_config(self) -> SiteConfig:
        raw = self._read_json(self.config_path, default=None)
        if raw is None:
            return SiteConfig(updated_at="")
        try:
            return SiteConfig(**{k: v for k, v in raw.items() if k in SiteConfig.model_fields})
        except Exception:
            return SiteConfig(updated_at="")

    def update_config(self, patch: SiteConfigUpdate) -> SiteConfig:
        cur = self.get_config()
        data = cur.model_dump()
        changed = False
        for field, value in patch.model_dump(exclude_unset=True).items():
            if value is not None and data.get(field) != value:
                data[field] = value
                changed = True
        if changed:
            data["updated_at"] = _now()
            self._write_json(self.config_path, data)
        return SiteConfig(**data)

    # ───────────────────────── 内部工具 ─────────────────────────

    @staticmethod
    def _read_json(path: Path, default: Any = None) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text())
        except Exception:
            return default

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, default=str, indent=2, ensure_ascii=False))
