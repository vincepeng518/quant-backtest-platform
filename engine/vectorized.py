"""
vectorized.py — DEPRECATED

This module was a minimal vectorized backtester (38 lines) that only supported
flat 0/1/-1 positions with no position management, slippage, or funding.

It was never used by the platform — all backtests go through the event-driven
Backtester (engine/backtester.py) or ReplayBacktester (engine/replay.py).

Kept as a stub for reference; will be removed in a future cleanup pass.
"""

from __future__ import annotations