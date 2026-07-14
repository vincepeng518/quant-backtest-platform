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


# ---------------------------------------------------------------------------
# 鏈上輪次 start/end price (Phase 1 目標價真值來源)
#
# predict.fun 的 BTC Up/Down 輪次由鏈上 ChainlinkUpDownAdapter 管理:
#   - 每輪有已知 startPrice (輪次開始價, 即 Phase 1 的「目標價」)
#   - 結算時用 Chainlink Data Streams v3 報告的 endPrice
# 這些可透過 conditionId 在 BSC 上讀取 (無需 auth)。
#
# 已知合約地址候選 (來自 docs.predict.fun): 0xf4aa30b537882eca7e69defb68d6f631cda77b00
# 待確認後填入下方 ADAPTER 並實作 getRound(conditionId) -> (startPrice, endPrice)。
# 在確認前, Phase 1 暫用 Binance 輪次開盤價當目標價近似 (已在 shadow_engine 實作)。
# ---------------------------------------------------------------------------
BSC_RPC = "https://bsc-dataseed.bnbchain.org"
_ADAPTER_CANDIDATE = "0xf4aa30b537882eca7e69defb68d6f631cda77b00"


def condition_start_price(condition_id: str) -> Optional[float]:
    """鏈上讀取輪次 startPrice (Phase 1 目標價真值)。

    待 ChainlinkUpDownAdapter 合約地址 + ABI 確認後實作。
    目前回傳 None -> 呼叫方回退 Binance 輪次開盤價近似。
    """
    # TODO: adapter = _ADAPTER_CANDIDATE; call getRound(conditionId)
    #   via BSC RPC eth_call, decode (startPrice, endPrice).
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    src = PredictFunSource()
    rounds = src.active_btc_rounds(limit=60)
    print(f"active BTC rounds: {len(rounds)}")
    for r in rounds[:5]:
        print(f"  {r['id']} | {r['question'][:45]} | bids={len(r['bids'])} asks={len(r['asks'])}")
        if r["bids"]:
            print(f"    top bid: {r['bids'][0]}")
    src.close()
