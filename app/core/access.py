"""app/core/access.py — PUBLIC_MODE 分級 + 全域守門。

recon（2026-09-17）發現後端所有資料端點無認證即可存取。此模組集中定義
「哪個路徑屬於哪一級」，並以 middleware 全域擋掉不該公開的請求，
避免逐個端點補 `Depends` 時漏掉。

分級：
  PUBLIC  — 永遠開放（health）
  READ    — 唯讀公開：symbols/ohlcv/templates/exchanges（demo 模式）
  COMPUTE — 無狀態運算：匿名可跑但結果不落庫（ephemeral）
  OWNER   — 需認證：history/results/admin/chat/import/experiments
"""

from __future__ import annotations

import os

# 永遠公開，任何模式都不擋
ALWAYS_PUBLIC = {"/health", "/", "/docs", "/openapi.json", "/redoc"}

# demo 模式下可匿名唯讀
PUBLIC_READ_PREFIXES = (
    "/api/data/symbols",
    "/api/data/ohlcv",
    "/api/strategy/templates",
    "/api/exchanges/",
    "/api/health",
)

# 匿名可執行，但結果必須 ephemeral（不寫 history / 不落庫）
ANON_COMPUTE_EXACT = {
    ("POST", "/api/backtest/run"),
    ("POST", "/api/analysis/walk-forward"),
    ("POST", "/api/analysis/monte-carlo"),
    ("POST", "/api/optimize/run"),
    ("POST", "/api/arbitrage/run"),
    ("POST", "/api/portfolio/run"),
}

# 機器對機器（用 x-monitor-key 自我驗證，不走 bearer）
MACHINE_PREFIXES = (
    "/api/monitoring/push",
    "/api/monitoring/heartbeat",
)

# 一律需 bearer 認證
OWNER_PREFIXES = (
    "/api/admin",
    "/api/chat",
    "/api/experiments",
    "/api/monitoring",   # 除 MACHINE_PREFIXES 外
    "/api/trades",
    "/api/validate",
    "/api/research",
    "/api/backtest/history",
    "/api/backtest/results",
    "/api/backtest/status",
    "/api/backtest/cancel",
    "/api/backtest/push-notion",
    "/api/strategy/user",
    "/api/strategy/upload",
)


def public_mode() -> str:
    """'demo'（預設，保留公開展示）或 'private'（未認證全擋）。"""
    return (os.getenv("PUBLIC_MODE") or "demo").strip().lower()


def is_always_public(path: str) -> bool:
    return path in ALWAYS_PUBLIC


def is_machine_route(path: str) -> bool:
    return any(path.startswith(p) for p in MACHINE_PREFIXES)


def is_public_read(path: str) -> bool:
    return any(path.startswith(p) for p in PUBLIC_READ_PREFIXES)


def is_anon_compute(method: str, path: str) -> bool:
    return (method.upper(), path) in ANON_COMPUTE_EXACT


def is_owner_route(path: str) -> bool:
    if is_machine_route(path):
        return False
    return any(path.startswith(p) for p in OWNER_PREFIXES)


def decide(method: str, path: str, authenticated: bool, has_machine_key: bool) -> str:
    """回傳 'allow' | 'deny' | 'ephemeral'。

    ephemeral = 放行但結果不得落庫（匿名運算）。
    """
    if is_always_public(path):
        return "allow"
    if is_machine_route(path):
        return "allow" if has_machine_key else "deny"
    if authenticated:
        return "allow"
    mode = public_mode()
    if mode == "private":
        return "deny"
    # demo 模式
    if is_owner_route(path):
        return "deny"
    if is_public_read(path):
        return "allow"
    if is_anon_compute(method, path):
        return "ephemeral"
    # 未分類的寫入/未知路徑 → 保守拒絕
    if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
        return "deny"
    return "deny"
