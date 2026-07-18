"""Minimal Telegram notifier for the monitoring daemon.

Reads TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID from env. If unset, send()
is a no-op (daemon keeps running, just no alerts). Avoids hard-failing the
monitoring loop on missing credentials.
"""
from __future__ import annotations

import os

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore[assignment]


def _cfg() -> tuple[str, str] | None:
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    cid = os.getenv("TELEGRAM_CHAT_ID")
    if not tok or not cid:
        return None
    return tok, cid


def send(message: str) -> bool:
    cfg = _cfg()
    if cfg is None or httpx is None:
        return False
    tok, cid = cfg
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            json={"chat_id": cid, "text": message, "parse_mode": "Markdown"},
            timeout=10.0,
        )
        return r.status_code == 200
    except Exception:
        return False


def alert(subject: str, detail: str = "") -> bool:
    """Convenience: formatted alert with a prefix tag."""
    msg = f"🚨 *monitoring* {subject}\n{detail}".strip()
    return send(msg)
