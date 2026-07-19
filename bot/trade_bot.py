"""
Trade Bot — 自動抓取 BingX 交易數據並永久寫入 GitHub。

抓取來源 (BingX swap API, 已驗證):
  - /openApi/swap/v2/user/positions  : 當前持倉 (開倉價/槓桿/未實現盈虧/清算價)
  - /openApi/swap/v2/user/income     : 已實現 PnL / 費用 / 資金費 (近3月)
  - /openApi/swap/v2/trade/allOrders : 訂單歷史 (開平價/方向/數量)

永久儲存: 調用 app.services.strategy_git 寫入 GitHub repo 的 trades/ 目錄
  (git-tracked, 不會因容器重啟/重建丟失, 與 backtest_history/ 同機制)

客觀欄位 (不含情緒/策略主觀填寫):
  symbol, side, positionAmt, avgPrice(開), exitPrice(平), leverage,
  unrealizedProfit / realizedProfit(盈虧), pnlRatio(盈虧比),
  positionValue(總倉位大小), liquidationPrice, closeTime

用法:
  python bot/trade_bot.py            # 抓一次, 寫一筆快照
  python bot/trade_bot.py --daemon   # 每 300s 跑一次 (或由 systemd timer 調用)
"""
from __future__ import annotations
import os, sys, time, json, argparse, logging, base64, urllib.request, urllib.error
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("trade_bot")

# 讓此檔能 import app.services.strategy_git
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from app.services.strategy_git import git_persist, REPO  # type: ignore
except Exception as e:  # noqa
    logger.warning("strategy_git import failed: %s", e)
    git_persist = None
    REPO = "vincepeng518/quant-backtest-platform"

# ccxt 統一交易所介面 (抓持倉, 穩定)
try:
    import ccxt
except Exception as e:  # noqa
    logger.warning("ccxt import failed: %s", e)
    ccxt = None

# 私有簽名僅用於抓歷史成交 (ccxt 無法逐 symbol 掃歷史 allOrders)
import hmac as _hmac
import hashlib as _hashlib
import requests as _requests

BASE = "https://open-api.bingx.com"


def _sign(path: str, params: dict) -> str:
    qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = os.environ.get("BINGX_API_SECRET", "")
    sig = _hmac.new(secret.encode(), qs.encode(), _hashlib.sha256).hexdigest()
    return f"{path}?{qs}&signature={sig}"


def _call_private(path: str, params: dict | None = None) -> dict:
    params = params or {}
    params.update({"timestamp": int(time.time() * 1000), "recvWindow": 5000})
    url = f"{BASE}{_sign(path, params)}"
    try:
        r = _requests.get(url, headers={
            "X-BX-APIKEY": os.environ.get("BINGX_API_KEY", ""),
            "X-SOURCE-KEY": "BX-AI-SKILL",
        }, timeout=15)
        return r.json()
    except Exception as e:  # noqa
        logger.warning("private call %s err: %s", path, e)
        return {}


def _parse_lev(v) -> float:
    """BingX leverage 可能為 '150X' 字串 -> 150.0"""
    if v is None:
        return 0.0
    s = str(v).replace("X", "").replace("x", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


TRADES_PREFIX = "trades"  # GitHub 路徑 trades/


def _client():
    """建立 BingX ccxt client (從環境變數讀 key/secret)。"""
    if ccxt is None:
        return None
    return ccxt.bingx({
        "apiKey": os.environ.get("BINGX_API_KEY", ""),
        "secret": os.environ.get("BINGX_API_SECRET", ""),
        "enableRateLimit": True,
    })


def simplify_symbol(raw: str | None) -> str | None:
    """BingX symbol 簡化 (用戶規則):
    - Crypto:     BTC-USDT → BTC (也處理 ccxt 原始 ETH/USDT:USDT → ETH)
    - TradFi 商品: NCCOGOLD2USD-USDT → GOLD
    - TradFi 股票: NCSKTSLA2USD-USDT → TSLA
    - TradFi 股指: NCSINASDAQ1002USD-USDT → NASDAQ100
    - TradFi 外匯: NCFXEUR2USD-USDT → EUR/USD, NCFXGBP2JPY-USDT → GBP/JPY
    """
    if not raw:
        return raw
    import re
    s = raw.strip().replace("/", "-").replace(":USDT", "").replace(":USDC", "")
    # 外匯: NCFX<BASE>2<QUOTE>-USDT → BASE/QUOTE
    m = re.match(r"^NCFX(\w+?)2(\w+)-USDT$", s)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    # 商品/股票/股指: NC{CO|SK|SI}<NAME>2USD-USDT → NAME
    m = re.match(r"^NC(CO|SK|SI)(.+?)2USD-USDT$", s)
    if m:
        return m.group(2)
    # Crypto: 去尾部 -USDT
    if s.endswith("-USDT"):
        return s[: -len("-USDT")]
    return s


def fetch_positions() -> list:
    """用 ccxt 抓 BingX 持倉 (替代私有簽名 API)。"""
    ex = _client()
    if ex is None:
        logger.warning("ccxt client 不可用")
        return []
    try:
        raw = ex.fetch_positions()
        out = []
        for p in raw:
            sym = simplify_symbol(_ccxt_sym(p.get("symbol")))
            side = (p.get("side") or "").upper()  # long/short -> LONG/SHORT
            if not sym:
                continue
            out.append({
                "symbol": sym,
                "positionSide": side,
                "avgPrice": float(p.get("entryPrice") or 0),
                "leverage": float(p.get("leverage") or 0),
                "unrealizedProfit": float(p.get("unrealizedPnl") or 0),
                "realisedProfit": float(p.get("realizedPnl") or 0),
                "pnlRatio": 0.0,
                "positionValue": float(p.get("notional") or p.get("contracts") or 0),
                "liquidationPrice": float(p.get("liquidationPrice") or 0),
                "positionAmt": float(p.get("contracts") or p.get("amount") or 0),
            })
        return out
    except Exception as e:  # noqa
        logger.warning("ccxt positions err: %s", e)
        return []
        return []


def fetch_order_history(limit: int = 200) -> list:
    """私有 allOrders: 歷史成交 (含開平價, ccxt 無法逐 symbol 掃歷史)。"""
    try:
        d = _call_private("/openApi/swap/v2/trade/allOrders", {"limit": limit})
        data = d.get("data", {})
        if isinstance(data, dict):
            return data.get("orders", [])
        return data if isinstance(data, list) else []
    except Exception as e:  # noqa
        logger.warning("order history err: %s", e)
        return []


def build_snapshot() -> dict:
    """組合一次快照: 當前持倉 (ccxt) + 歷史成交 (私有 allOrders)。
    只記有開平價的完整數據 (過濾無價格的)。"""
    positions = fetch_positions()
    orders = fetch_order_history(200)

    recs = []
    # 1) 當前持倉 (ccxt, status=OPEN)
    for p in positions:
        sym = simplify_symbol(p.get("symbol"))
        pside = p.get("positionSide")  # LONG/SHORT
        avg = float(p.get("avgPrice", 0) or 0)
        amt = float(p.get("positionAmt", 0) or 0)
        if avg <= 0:  # 無開倉價不記
            continue
        recs.append({
            "symbol": sym,
            "side": pside,
            "positionAmt": amt,
            "avgPrice": avg,
            "exitPrice": 0.0,       # 持倉中尚未平倉
            "leverage": float(p.get("leverage", 0) or 0),
            "unrealizedProfit": float(p.get("unrealizedProfit", 0) or 0),
            "realizedProfit": float(p.get("realisedProfit", 0) or 0),
            "pnlRatio": 0.0,
            "positionValue": float(p.get("positionValue", 0) or 0),
            "liquidationPrice": float(p.get("liquidationPrice", 0) or 0),
            "status": "OPEN",
            "ts": int(time.time() * 1000),
        })

    # 2) 歷史成交 (私有 allOrders, FILLED 且有 avgPrice -> 完整開平價)
    seen_keys = set()
    for o in orders:
        if o.get("status") != "FILLED":
            continue
        sym = simplify_symbol(o.get("symbol"))
        pside = o.get("positionSide")  # LONG/SHORT
        avg = float(o.get("avgPrice", 0) or 0)
        if avg <= 0:  # 無價格不記 (過濾不完整數據)
            continue
        # 去重: 同一 symbol+side+positionSide+time 只記一次
        key = (sym, o.get("side"), pside, o.get("time"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        recs.append({
            "symbol": sym,
            "side": pside,
            "positionAmt": float(o.get("executedQty", 0) or 0),
            "avgPrice": avg,            # 成交價 (開或平)
            "exitPrice": avg,           # 歷史成交有完整價格
            "leverage": _parse_lev(o.get("leverage")),
            "unrealizedProfit": 0.0,
            "realizedProfit": float(o.get("profit", 0) or 0),
            "pnlRatio": 0.0,
            "positionValue": float(o.get("cumQuote", 0) or 0),
            "liquidationPrice": 0.0,
            "status": "CLOSED",
            "ts": int(o.get("time", 0) or 0),
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "bingx-ccxt+orders",
        "repo": REPO,
        "count": len(recs),
        "records": recs,
    }


def _gh_put(path: str, content: str, message: str) -> tuple[bool, str]:
    """直接寫 GitHub contents API 到 trades/ 目錄。"""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return False, "GITHUB_TOKEN missing"
    h = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"}
    api = f"https://api.github.com/repos/{REPO}/contents/{path}"
    # 查現有 sha (更新用)
    existing = None
    try:
        with urllib.request.urlopen(urllib.request.Request(api, headers=h), timeout=20) as r:
            existing = json.loads(r.read().decode())
    except Exception:
        existing = None
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": "master",
    }
    if existing and existing.get("sha"):
        payload["sha"] = existing["sha"]
    req = urllib.request.Request(api, data=json.dumps(payload).encode(), method="PUT", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return True, "pushed" if r.status == 201 or r.status == 200 else str(r.status)
    except Exception as e:  # noqa
        return False, str(e)[:200]


def persist(snap: dict) -> str:
    """寫入本地 + 永久 GitHub trades/ 目錄。"""
    os.makedirs(os.path.join(ROOT, TRADES_PREFIX), exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"trades_{ts}.json"
    local = os.path.join(ROOT, TRADES_PREFIX, fname)
    with open(local, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    logger.info("local written: %s (%d records)", local, snap["count"])

    ok, detail = _gh_put(f"{TRADES_PREFIX}/{fname}", json.dumps(snap, ensure_ascii=False, indent=2), f"trade bot: {fname}")
    logger.info("github persist: %s %s", ok, detail)
    return fname


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon", action="store_true", help="每300s循環")
    ap.add_argument("--interval", type=int, default=300)
    args = ap.parse_args()

    if not os.environ.get("BINGX_API_KEY") or not os.environ.get("BINGX_API_SECRET"):
        logger.error("BINGX_API_KEY / BINGX_API_SECRET 未設置")
        raise SystemExit(1)

    if args.daemon:
        logger.info("daemon mode, interval=%ss", args.interval)
        while True:
            try:
                snap = build_snapshot()
                persist(snap)
            except Exception as e:  # noqa
                logger.exception("loop err: %s", e)
            time.sleep(args.interval)
    else:
        snap = build_snapshot()
        fname = persist(snap)
        print(f"OK {fname} records={snap['count']}")


if __name__ == "__main__":
    main()
