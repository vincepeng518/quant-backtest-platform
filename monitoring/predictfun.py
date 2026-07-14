from __future__ import annotations

import json
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GRAPHQL_ENDPOINT = "https://graphql.predict.fun/graphql"

# 找活躍 BTC Up/Down 輪次的 query
_Q_MARKETS = """
query ActiveBtcRounds($first: Int!) {
  markets(pagination: {first: $first}) {
    edges {
      node {
        id
        question
        conditionId
        createdAt
        outcomes { edges { node { id } } }
        orderbook { bids asks lastOrderSettled { price kind side outcome } }
      }
    }
  }
}
"""

_Q_ORDERBOOK = """
query GetOrderbook($id: ID!) {
  market(id: $id) {
    id
    conditionId
    outcomes { edges { node { id } } }
    orderbook { bids asks lastOrderSettled { price kind side outcome } }
  }
}
"""


class PredictFunSource:
    """predict.fun GraphQL 數據源 (公開, 無需 auth)。

    提供:
      - 活躍的 BTC Up/Down 5分鐘輪次 (id, conditionId, outcomes)
      - 每個輪次的訂單簿深度 (Phase 2 賠率/流動性檢測)
    """

    def __init__(self, endpoint: str = GRAPHQL_ENDPOINT, timeout: float = 10.0):
        self.endpoint = endpoint
        self._client = httpx.Client(timeout=timeout, headers={"Content-Type": "application/json"})
        self._cache_ttl = 15.0
        self._cache: dict = {}
        self._cache_ts: float = 0.0

    def _gql(self, query: str, variables: dict) -> Optional[dict]:
        try:
            r = self._client.post(self.endpoint, content=json.dumps({"query": query, "variables": variables}))
            if r.status_code != 200:
                logger.warning("[PREDICT] HTTP %s: %s", r.status_code, r.text[:200])
                return None
            data = r.json()
            if "errors" in data:
                logger.warning("[PREDICT] gql errors: %s", str(data["errors"])[:200])
                return None
            return data.get("data")
        except Exception as e:
            logger.warning("[PREDICT] request failed: %s", e)
            return None

    def active_btc_rounds(self, limit: int = 60, use_cache: bool = True) -> list[dict]:
        """返回活躍的 BTC Up/Down 輪次列表 (訂單簿非空的)。"""
        now = time.time()
        if use_cache and (now - self._cache_ts) < self._cache_ttl and "rounds" in self._cache:
            return self._cache["rounds"]

        data = self._gql(_Q_MARKETS, {"first": limit})
        if not data:
            return self._cache.get("rounds", [])

        out = []
        for e in data["markets"]["edges"]:
            n = e["node"]
            q = (n.get("question") or "").upper()
            if "BITCOIN UP OR DOWN" not in q:
                continue
            ob = n.get("orderbook") or {}
            bids = ob.get("bids") or []
            asks = ob.get("asks") or []
            if not bids and not asks:
                continue  # 已結算/流動性空 → 跳過
            oc = n.get("outcomes") or {}
            oc_edges = oc.get("edges") or []
            outc = [o["node"]["id"] for o in oc_edges]
            out.append({
                "id": n["id"],
                "question": n["question"],
                "condition_id": n.get("conditionId"),
                "created_at": n.get("createdAt"),
                "outcomes": outc,            # [up_id, down_id]
                "bids": bids,                  # [[price, size], ...]
                "asks": asks,
                "last_settled": ob.get("lastOrderSettled"),
            })
        self._cache = {"rounds": out}
        self._cache_ts = now
        return out

    def book_for(self, market_id: str) -> Optional[dict]:
        data = self._gql(_Q_ORDERBOOK, {"id": market_id})
        if not data or not data.get("market"):
            return None
        m = data["market"]
        ob = m.get("orderbook") or {}
        return {
            "id": m["id"],
            "condition_id": m.get("conditionId"),
            "bids": ob.get("bids") or [],
            "asks": ob.get("asks") or [],
            "last_settled": ob.get("lastOrderSettled"),
        }

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass


class PredictFunRest:
    """predict.fun REST 數據源 (需 API Key, 主網所有端點都要)。

    提供 Phase 1 / Phase 4 的真值:
      - variantData.startPrice: 輪次開始價 (Phase 1 的「目標價」真值)
      - variantData.endPrice:   輪次結算價 (Phase 4 的結算真值)
      - variantData.priceFeedId: Pyth/Chainlink feed id
    這些 GraphQL 沒有, 只在 REST /v1/markets 提供。
    """

    BASE = "https://api.predict.fun/v1"

    def __init__(self, api_key: str, timeout: float = 12.0):
        self.api_key = api_key
        self._client = httpx.Client(
            timeout=timeout,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
        )
        self._cache_ttl = 30.0
        self._cache: dict = {}
        self._cache_ts: float = 0.0

    def _get(self, path: str, params: dict | None = None) -> Optional[dict]:
        try:
            r = self._client.get(self.BASE + path, params=params)
            if r.status_code != 200:
                logger.warning("[PREDICT-REST] HTTP %s: %s", r.status_code, r.text[:200])
                return None
            return r.json()
        except Exception as e:
            logger.warning("[PREDICT-REST] request failed: %s", e)
            return None

    def btc_rounds(self, status: str = "OPEN", limit: int = 50,
                   use_cache: bool = True) -> list[dict]:
        """返回 BTC Up/Down 輪次 (含 variantData.startPrice/endPrice 真值)。"""
        now = time.time()
        cache_key = f"{status}:{limit}"
        if use_cache and (now - self._cache_ts) < self._cache_ttl and cache_key in self._cache:
            return self._cache[cache_key]

        d = self._get("/markets", {"first": str(limit),
                                    "marketVariant": "CRYPTO_UP_DOWN",
                                    "status": status})
        if not d or d.get("success") is False or "data" not in d:
            return self._cache.get(cache_key, [])
        markets = d["data"]
        if not isinstance(markets, list):
            markets = markets.get("markets", [])

        out = []
        for m in markets:
            q = (m.get("question") or "").upper()
            if "BITCOIN UP OR DOWN" not in q:
                continue
            vd = m.get("variantData") or {}
            out.append({
                "id": m["id"],
                "question": m["question"],
                "condition_id": m.get("conditionId"),
                "status": m.get("status"),
                "start_price": vd.get("startPrice"),   # Phase 1 真值
                "end_price": vd.get("endPrice"),       # Phase 4 真值
                "price_feed_id": vd.get("priceFeedId"),
                "created_at": m.get("createdAt"),
            })
        self._cache[cache_key] = out
        self._cache_ts = now
        return out

    def start_price_for(self, market_id: str) -> Optional[float]:
        """單一輪次的 startPrice (Phase 1 真值)。None 表示輪次尚未開始。"""
        d = self._get(f"/markets/{market_id}")
        if not d or "data" not in d:
            return None
        m = d["data"] if isinstance(d["data"], dict) else (d["data"][0] if d.get("data") else {})
        vd = (m or {}).get("variantData") or {}
        return vd.get("startPrice")

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass

# ---------------------------------------------------------------------------
# [DEPRECATED] 鏈上輪次 start/end price
#
# 原計畫: 透過 conditionId 在 BSC 上讀 ChainlinkUpDownAdapter 拿 startPrice。
# 實際確認: predict.fun 用的是 **Pyth Network** 喂價 (variantData.priceFeedId),
#   且 REST /v1/markets 的 variantData.startPrice / endPrice 已直接提供真值
#   (需 API Key, 已由 PredictFunRest 實作並接進 ShadowEngine.target_provider)。
#   => 鏈上讀取已不再需要, 下方函數保留為 stub (回傳 None)。
# ---------------------------------------------------------------------------


def condition_start_price(condition_id: str) -> Optional[float]:
    """[DEPRECATED] 鏈上 startPrice。現由 PredictFunRest 提供, 此處永遠回傳 None。"""
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # REST 真值源示範
    from monitoring.config import MonitorConfig
    cfg = MonitorConfig.load()
    if cfg.api_key:
        rest = PredictFunRest(cfg.api_key)
        rs = rest.btc_rounds(status="OPEN", limit=10)
        print(f"OPEN BTC rounds (REST, real startPrice): {len(rs)}")
        for r in rs[:5]:
            print(f"  {r['id']} | {r['question'][:40]} | start={r['start_price']} end={r['end_price']}")
        rest.close()
    else:
        print("no api_key in config; skipping REST demo")

