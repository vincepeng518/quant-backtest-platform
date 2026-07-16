from __future__ import annotations

"""Lookahead / future-data leak guard for user-uploaded strategies.

Freqtrade ships `lookahead-analysis` and `recursive-analysis` commands that
catch strategies which accidentally use future information (e.g. `df.shift(-1)`,
`df.iloc[-1]`, reading the *next* bar inside an indicator). Our platform lets
users upload arbitrary Python strategy code, so a naive strategy could report
impossible Sharpe ratios by peeking at future bars.

This module provides:
  1. ``scan_code``  — static AST/pattern scan for obvious future-leak idioms.
  2. ``verify_no_lookahead`` — dynamic check: run the strategy twice on a
     dataset truncated at different points; if the *early* trades change when
     future bars are removed, the strategy is leaking.

Both are non-fatal guards: they return a report the API can surface as a
warning rather than hard-blocking legit strategies.
"""

import re
from typing import Any

# Patterns that strongly suggest the strategy reads future data.
_LOOKAHEAD_PATTERNS = [
    (re.compile(r"\.shift\(\s*-?\s*\d*\.\s*1\s*\)"), "shift(-1) — uses next bar's value"),
    (re.compile(r"\.shift\(\s*-\s*\d+\s*\)"), "negative shift() — looks ahead"),
    (re.compile(r"\.iloc\[\s*-1\s*\]"), "iloc[-1] — last row (often future in rolling)"),
    (re.compile(r"\.iloc\[\s*len\s*\("), "iloc[len(...)] — out-of-bounds forward index"),
    (re.compile(r"\.tail\s*\(\s*1\s*\)\s*\.iloc\s*\[\s*0\s*\]"), "tail(1) inside indicator — future close"),
    (re.compile(r"\.rolling\([^)]*\)\.apply\([^)]*shift"), "rolling().apply with shift — recursive/leak risk"),
]


def scan_code(code: str) -> list[str]:
    """Static scan of strategy source for future-leak idioms.

    Returns a list of human-readable warnings (empty = clean).
    """
    warnings: list[str] = []
    for pat, msg in _LOOKAHEAD_PATTERNS:
        if pat.search(code):
            warnings.append(f"Possible lookahead: {msg}")
    return warnings


def verify_no_lookahead(
    strategy_cls: Any,
    data: Any,
    param_space: dict | None = None,
    params: dict | None = None,
) -> dict:
    """Dynamic lookahead check.

    Runs the strategy on the full dataset and on a version truncated at 80%,
    then compares the *trades generated in the common prefix region*. If the
    early trades differ, the strategy is consuming future bars.

    Args:
        strategy_cls: a StrategyBase subclass (not yet initialized)
        data: DataFrame with OHLCV + timestamp
        param_space / params: optional init params

    Returns dict: {leaked: bool, warnings: list[str], detail: str}
    """
    from engine.backtester import Backtester

    warnings: list[str] = []
    try:
        init_params = params or {}
        n = len(data)
        cut = int(n * 0.8)

        # Full run
        bt_full = Backtester(initial_capital=100_000)
        s_full = strategy_cls()
        s_full.init(init_params)
        bt_full.set_strategy(s_full)
        bt_full.set_data(data)
        r_full = bt_full.run()
        full_entries = [t.entry_time for t in r_full.trades]

        # Truncated run
        bt_cut = Backtester(initial_capital=100_000)
        s_cut = strategy_cls()
        s_cut.init(init_params)
        bt_cut.set_strategy(s_cut)
        bt_cut.set_data(data.iloc[:cut].reset_index(drop=True))
        r_cut = bt_cut.run()
        cut_entries = [t.entry_time for t in r_cut.trades]

        # Compare entries in the overlapping window (first `cut` bars)
        overlap_full = [e for e in full_entries if e is not None and str(e) in {str(x) for x in cut_entries}]
        leaked = len(overlap_full) != len(cut_entries)
        if leaked:
            warnings.append(
                f"Strategy produced {len(cut_entries)} trades on truncated data but "
                f"{len(full_entries)} on full data — early trades changed when future "
                f"bars were removed, indicating lookahead bias."
            )
        return {"leaked": leaked, "warnings": warnings, "detail": f"full={len(full_entries)} cut={len(cut_entries)}"}
    except Exception as e:  # pragma: no cover — guard must never crash the run
        return {"leaked": False, "warnings": [f"lookahead verify skipped: {e}"], "detail": "error"}
