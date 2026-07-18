"""Push backtest results to Notion (回測紀錄庫, NOT ATM 策略庫).

Uses NOTION_TOKEN (from /root/.env) + NOTION_BACKTEST_PAGE_ID (target page).
Appends a heading + metric bullets + trade table as children blocks.
If NOTION_BACKTEST_PAGE_ID unset, push() is a no-op (caller decides whether to warn).
IMPORTANT: ATM 是特定策略回測庫, 此模組推的是獨立「回測紀錄庫」, 不污染 ATM.
"""
from __future__ import annotations

import os

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

_NOTION_API = "https://api.notion.com/v1"


def _headers() -> dict | None:
    tok = os.getenv("NOTION_TOKEN")
    if not tok:
        return None
    return {
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }


def _blocks_for(result: dict, symbol: str, strategy: str, timeframe: str) -> list[dict]:
    m = result.get("metrics", {})
    blocks: list[dict] = [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text",
                "text": {"content": f"回測 · {symbol} · {strategy} · {timeframe}"}}]},
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text",
                "text": {"content": f"總報酬: {m.get('total_return_pct', 0):.2f}%  |  Sharpe: {m.get('sharpe_ratio', 0):.2f}  |  最大回撤: {m.get('max_drawdown_pct', 0):.2f}%"}}]},
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text",
                "text": {"content": f"交易數: {m.get('total_trades', 0)}  |  勝率: {m.get('win_rate', 0):.1f}%  |  Profit Factor: {m.get('profit_factor', 0):.2f}"}}]},
        },
    ]
    trades = result.get("trades", [])[:20]
    if trades:
        rows = "| # | Entry | Exit | PnL |"
        for i, t in enumerate(trades, 1):
            rows += f"\n| {i} | {t.get('entry_price', '-')} | {t.get('exit_price', '-')} | {t.get('pnl', 0):.2f} |"
        blocks.append({
            "object": "block",
            "type": "table",
            "table": {
                "table_width": 4,
                "has_column_header": True,
                "has_row_header": False,
                "children": [_row(r) for r in rows.strip().split("\n")],
            },
        })
    return blocks


def _row(text: str) -> dict:
    cells = text.split("|")
    cells = [c.strip() for c in cells if c.strip() != ""]
    return {
        "object": "block",
        "type": "table_row",
        "table_row": {"cells": [[{"type": "text", "text": {"content": c}}] for c in cells]},
    }


def push(result: dict, symbol: str, strategy: str, timeframe: str) -> bool:
    """Append backtest summary to the BACKTEST RECORDS page (NOT ATM strategy lib).
    Uses NOTION_BACKTEST_PAGE_ID. If unset, no-op."""
    page_id = os.getenv("NOTION_BACKTEST_PAGE_ID")
    headers = _headers()
    if not page_id or not headers or httpx is None:
        return False
    blocks = _blocks_for(result, symbol, strategy, timeframe)
    try:
        r = httpx.patch(
            f"{_NOTION_API}/blocks/{page_id}/children",
            headers=headers,
            json={"children": blocks},
            timeout=20.0,
        )
        return r.status_code in (200, 201)
    except Exception:
        return False
