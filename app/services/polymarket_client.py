"""Polymarket CLOB client — market data + order placement.

Uses env: POLYMARKET_API_KEY, POLYMARKET_ADDRESS, POLYMARKET_PRIVATE_KEY.

SECURITY MODEL:
- Private key lives only in .env (gitignored). Never log it.
- place_order() requires explicit execute=True. WITHOUT it, the function
  builds + signs the order but does NOT submit (dry-run, returns the signed blob).
- There is NO auto-trading loop. Every fill requires an explicit call.

CLOB REST base: https://clob.polymarket.com
Relayer: https://relayer-v2.polymarket.com/submit
Chain: Polygon (chain_id=137)
"""
from __future__ import annotations

import os

import requests

_CLOB = "https://clob.polymarket.com"
_CHAIN_ID = 137  # Polygon mainnet
_HEADERS = {"Content-Type": "application/json"}
_key = os.getenv("POLYMARKET_API_KEY")
if _key:
    _HEADERS["POLY-API-KEY"] = _key


def get_markets(limit: int = 20, next_cursor: str = "", active_only: bool = True) -> dict:
    """List markets. Returns raw CLOB response.

    active_only: filter to active + order-accepting markets (skip closed/old).
    """
    params = {"limit": limit}
    if next_cursor:
        params["cursor"] = next_cursor
    r = requests.get(f"{_CLOB}/markets", params=params, headers=_HEADERS, timeout=20.0)
    r.raise_for_status()
    data = r.json()
    if active_only:
        data["data"] = [
            m for m in data.get("data", [])
            if m.get("active") and m.get("accepting_orders")
        ]
    return data


def get_market(condition_id: str) -> dict:
    r = requests.get(f"{_CLOB}/market/{condition_id}", headers=_HEADERS, timeout=20.0)
    r.raise_for_status()
    return r.json()


def get_simplified_markets(limit: int = 10, active_only: bool = True) -> list[dict]:
    """Flatten markets to {condition_id, question, outcomes:[{token_id, price}]}.

    price = tokens[].price from CLOB market response (already provided,
    no extra /book call needed). Falls back to None.
    """
    data = get_markets(limit=limit, active_only=active_only)
    out = []
    for m in data.get("data", []):
        outcomes = []
        for t in m.get("tokens", []):
            tid = t.get("token_id")
            raw = t.get("price")
            try:
                price = float(raw) if raw is not None else None
            except (TypeError, ValueError):
                price = None
            outcomes.append({"token_id": tid, "price": price})
        out.append({
            "condition_id": m.get("condition_id"),
            "question": m.get("question"),
            "outcomes": outcomes,
        })
    return out


def _clob_client():
    """Build a signed ClobClient from env creds. Raises if priv key missing."""
    from py_clob_client_v2.client import ClobClient
    from py_clob_client_v2.clob_types import ApiCreds
    pk = os.getenv("POLYMARKET_PRIVATE_KEY")
    if not pk:
        raise RuntimeError("POLYMARKET_PRIVATE_KEY not set")
    # passphrase optional (some Polymarket keys have none)
    passphrase = os.getenv("POLYMARKET_PASSPHRASE", "")
    creds = ApiCreds(
        api_key=_key or "",
        api_secret=pk,
        api_passphrase=passphrase,
    )
    return ClobClient(
        host=_CLOB,
        chain_id=_CHAIN_ID,
        key=pk,  # Signer uses private key for L1 signing
        creds=creds,
        signature_type=0,  # Polymarket CLOB current: EIP-712 v2
    )


def place_order(
    token_id: str,
    price: float,
    size: float,
    side: str = "BUY",
    execute: bool = False,
):
    """Place (or dry-run) an order on a Polymarket outcome token.

    side: "BUY" | "SELL"
    execute=False -> build + sign, return the order blob, DO NOT submit.
    execute=True  -> submit via relayer. Returns the relayer response.

    SECURITY: defaults to dry-run. Never call with execute=True unless
    the user explicitly asked to place the order.
    """
    from py_clob_client_v2.clob_types import ApiCreds, OrderArgsV2
    pk = os.getenv("POLYMARKET_PRIVATE_KEY")
    if not pk:
        raise RuntimeError("POLYMARKET_PRIVATE_KEY not set")
    passphrase = os.getenv("POLYMARKET_PASSPHRASE", "")
    creds = ApiCreds(
        api_key=_key or "",
        api_secret=pk,
        api_passphrase=passphrase,
    )
    client = _clob_client()
    # derive L2 creds from private key (L1 signature) -> Polymarket CLOB creds
    derived = client.derive_api_key()
    if derived is None:
        raise RuntimeError("derive_api_key failed (no L2 creds for this wallet)")
    client.set_api_creds(derived)
    order_args = OrderArgsV2(
        token_id=token_id,
        price=price,
        size=size,
        side=side,
    )
    if not execute:
        signed = client.create_order(order_args)
        return {"submitted": False, "signed_order": signed, "note": "dry-run; pass execute=True to submit"}
    resp = client.create_and_post_order(order_args)
    return {"submitted": True, "response": resp}


if __name__ == "__main__":
    import json
    print(json.dumps(get_simplified_markets(5), indent=2, ensure_ascii=False))
