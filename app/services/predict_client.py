"""Predict.fun client — read-only market data + order building + dry-run.

Follows the X tutorial (ada0211dada) dev order:
  1. read-only market/orderbook  (API key, no auth)
  2. order construction          (predict-sdk OrderBuilder + private key sign)
  3. dry-run preview             (sign but DO NOT broadcast)
  4. live preflight              (TODO: gas/balance/approval checks)
  5. real on-chain submit        (TODO: web3 broadcast — requires BNB + USDT)

Chain: BNB Smart Chain (ChainId.BNB_MAINNET = 56).
Private key stays in env (PREDICT_PRIVATE_KEY), never logged.
JWT / REST private endpoints are NOT used here — Predict orders are on-chain
signed typed-data broadcast to the CTF Exchange contract.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from eth_account import Account

from predict_sdk import (
    ChainId,
    OrderBuilder,
    Side,
    BuildOrderInput,
    LimitHelperInput,
)

logger = logging.getLogger(__name__)

_BASE = "https://api.predict.fun/v1"


@dataclass
class PredictMarket:
    id: str
    question: str
    status: str
    token_id: Optional[str] = None
    start_price: Optional[float] = None
    end_price: Optional[float] = None


@dataclass
class DryRunOrder:
    ok: bool
    side: str
    token_id: str
    price: float
    qty: float
    maker_amount: str = ""
    taker_amount: str = ""
    signature: str = ""
    error: Optional[str] = None


class PredictClient:
    def __init__(self, api_key: str, private_key: Optional[str] = None, timeout: float = 12.0):
        self.api_key = api_key
        self.private_key = private_key
        self._client = requests.Session()
        self._client.headers.update({"x-api-key": api_key, "Content-Type": "application/json"})
        self._timeout = timeout
        self._builder = None
        if private_key:
            self._builder = OrderBuilder.make(ChainId.BNB_MAINNET, private_key)

    # ── Step 1: read-only ───────────────────────────────────────────────
    def get_markets(self, status: str = "OPEN", limit: int = 50, variant: str = "CRYPTO_UP_DOWN") -> list[PredictMarket]:
        try:
            r = self._client.get(f"{_BASE}/markets", params={
                "first": str(limit), "marketVariant": variant, "status": status,
            }, timeout=self._timeout)
            if r.status_code != 200:
                logger.warning("[PREDICT] markets HTTP %s: %s", r.status_code, r.text[:200])
                return []
            d = r.json()
        except Exception as e:
            logger.warning("[PREDICT] markets failed: %s", e)
            return []
        if not d.get("success") and "data" not in d:
            return []
        markets = d.get("data") or []
        out = []
        for m in markets:
            vd = m.get("variantData") or {}
            # token_id: derive from conditionId + index (Up=2 / Down=1 for neg-risk)
            out.append(PredictMarket(
                id=str(m.get("id")),
                question=m.get("question", ""),
                status=m.get("status", ""),
                start_price=vd.get("startPrice"),
                end_price=vd.get("endPrice"),
            ))
        return out

    def get_orderbook(self, market_id: str) -> Optional[dict]:
        try:
            r = self._client.get(f"{_BASE}/markets/{market_id}/orderbook", timeout=self._timeout)
            if r.status_code != 200:
                logger.warning("[PREDICT] orderbook HTTP %s", r.status_code)
                return None
            return r.json()
        except Exception as e:
            logger.warning("[PREDICT] orderbook failed: %s", e)
            return None

    def get_market_detail(self, market_id: str) -> Optional[dict]:
        """GET /markets/{id} — token ids live here (conditionId-based)."""
        try:
            r = self._client.get(f"{_BASE}/markets/{market_id}", timeout=self._timeout)
            if r.status_code != 200:
                return None
            return r.json()
        except Exception:
            return None

    # ── Step 2+3: build + dry-run sign (no broadcast) ───────────────────
    def build_dry_run(self, token_id: str, side: str, price: float, qty: float,
                      fee_rate_bps: int = 100) -> DryRunOrder:
        """Sign an order locally. Does NOT submit on-chain.

        side: "BUY" | "SELL"
        price: USDT per share (float)
        qty: number of shares (float)
        Returns DryRunOrder with signature if ok.
        """
        if self._builder is None:
            return DryRunOrder(False, side, token_id, price, qty,
                               error="no private key — cannot sign")
        try:
            side_enum = Side.BUY if side.upper() == "BUY" else Side.SELL
            # price/qty in wei (18 decimals)
            price_wei = int(price * 10**18)
            qty_wei = int(qty * 10**18)
            amounts = self._builder.get_limit_order_amounts(LimitHelperInput(
                side=side_enum, price_per_share_wei=price_wei, quantity_wei=qty_wei,
            ))
            order = self._builder.build_order("LIMIT", BuildOrderInput(
                side=side_enum, token_id=token_id,
                maker_amount=str(amounts.maker_amount),
                taker_amount=str(amounts.taker_amount),
                fee_rate_bps=fee_rate_bps,
            ))
            typed_data = self._builder.build_typed_data(
                order, is_neg_risk=False, is_yield_bearing=False,
            )
            signed = self._builder.sign_typed_data_order(typed_data)
            return DryRunOrder(
                ok=True, side=side, token_id=token_id, price=price, qty=qty,
                maker_amount=str(amounts.maker_amount),
                taker_amount=str(amounts.taker_amount),
                signature=signed.signature,
            )
        except Exception as e:
            logger.exception("[PREDICT] build_dry_run failed")
            return DryRunOrder(False, side, token_id, price, qty, error=str(e))


def from_env() -> PredictClient:
    api = os.getenv("PREDICT_API_KEY")
    pk = os.getenv("PREDICT_PRIVATE_KEY")
    if not api:
        raise RuntimeError("PREDICT_API_KEY not set")
    return PredictClient(api, pk)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    c = from_env()
    markets = c.get_markets(limit=5)
    print(f"OPEN markets: {len(markets)}")
    for m in markets[:3]:
        print(f"  {m.id} | {m.question[:40]} | start={m.start_price}")
    if markets and c._builder:
        detail = c.get_market_detail(markets[0].id)
        print("detail keys:", list((detail or {}).keys())[:10])
