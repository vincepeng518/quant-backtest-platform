#!/usr/bin/env python3
"""pixelrag_search.py — PixelRAG 視覺搜索 wrapper (接在平時搜尋能力上)。
用法:
  python3 pixelrag_search.py "<query>" [n_docs=5]
依賴: 免 key, 直接打 https://api.pixelrag.ai/search (8.28M Wikipedia 視覺索引)
返回: 相關文章 URL + score (視覺相似, 非文字匹配)
"""
import sys, json, urllib.request

API = "https://api.pixelrag.ai/search"

def search(query: str, n_docs: int = 5) -> list:
    payload = json.dumps({"queries": [{"text": query}], "n_docs": n_docs}).encode()
    req = urllib.request.Request(API, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    out = []
    for q in data.get("results", []):
        for hit in q.get("hits", []):
            out.append({"url": hit.get("url"), "score": round(hit.get("score", 0), 3)})
    return out

if __name__ == "__main__":
    q = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    for r in search(q, n):
        print(f"{r['score']:.3f}  {r['url']}")
