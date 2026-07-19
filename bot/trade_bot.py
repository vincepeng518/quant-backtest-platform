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

import hmac, hashlib, requests

BASE = "https://open-api.bingx.com"
TRADES_PREFIX = "trades"  # GitHub 路徑 trades/


def _sign(path: str, params: dict) -> str:
    qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = os.environ.get("BINGX_API_SECRET", "")
    sig = hmac.new(secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
    return f"{path}?{qs}&signature={sig}"


def _call(path: str, params: dict | None = None) -> dict:
    params = params or {}
    params.update({"timestamp": int(time.time() * 1000), "recvWindow": 5000})
    url = f"{BASE}{_sign(path, params)}"
    r = requests.get(url, headers={
        "X-BX-APIKEY": os.environ.get("BINGX_API_KEY", ""),
        "X-SOURCE-KEY": "BX-AI-SKILL",
    }, timeout=15)
    return r.json()


# symbol 簡化映射 (BingX 長名 -> 好讀)
SYMBOL_MAP = {
    "NCCOGOLD2USD-USDT": "GOLD-USDT",
}

def norm_sym(sym: str | None) -> str | None:
    if not sym:
        return sym
    return SYMBOL_MAP.get(sym, sym)


def fetch_positions() -> list:
    try:
        d = _call("/openApi/swap/v2/user/positions").get("data", [])
        return d if isinstance(d, list) else []
    except Exception as e:  # noqa
        logger.warning("positions err: %s", e)
        return []


def fetch_income(income_type: str = "REALIZED_PNL", limit: int = 200) -> list:
    try:
        d = _call("/openApi/swap/v2/user/income",
                  {"incomeType": income_type, "limit": limit}).get("data", [])
        return d if isinstance(d, list) else []
    except Exception as e:  # noqa
        logger.warning("income err: %s", e)
        return []


def fetch_orders(symbol: str | None = None, limit: int = 100) -> list:
    try:
        p = {"limit": limit}
        if symbol:
            p["symbol"] = symbol
        d = _call("/openApi/swap/v2/trade/allOrders", p).get("data", {})
        # allOrders 回傳 {"orders": [...]}
        if isinstance(d, dict):
            return d.get("orders", [])
        return d if isinstance(d, list) else []
    except Exception as e:  # noqa
        logger.warning("orders err: %s", e)
        return []


def build_snapshot() -> dict:
    """組合一次快照: 持倉 + 近期已實現PnL + 訂單歷史。"""
    positions = fetch_positions()
    realized = fetch_income("REALIZED_PNL", 200)
    orders = fetch_orders(limit=200)

    # 用 orders 補 exit price (平倉單 avgPrice)
    # order side: SELL+SHORT=LONG平倉; BUY+LONG=SHORT平倉
    exit_prices = {}
    for o in orders:
        sym = o.get("symbol")
        side = o.get("side")
        pside = o.get("positionSide")
        avg = float(o.get("avgPrice", 0) or 0)
        if sym and avg > 0:
            key = (sym, pside)
            exit_prices.setdefault(key, avg)

    recs = []
    for p in positions:
        sym = norm_sym(p.get("symbol"))
        pside = p.get("positionSide")  # LONG/SHORT
        avg = float(p.get("avgPrice", 0) or 0)
        lev = float(p.get("leverage", 0) or 0)
        upnl = float(p.get("unrealizedProfit", 0) or 0)
        rpnl = float(p.get("realisedProfit", 0) or 0)
        pnl_ratio = float(p.get("pnlRatio", 0) or 0)
        pval = float(p.get("positionValue", 0) or 0)
        liq = float(p.get("liquidationPrice", 0) or 0)
        amt = float(p.get("positionAmt", 0) or 0)
        # 持倉中尚未平倉: exit price 強制 0 (orders 推的不可靠, 避免偽造平倉價)
        exit_px = 0.0
        # 過濾: 開倉價與平倉價都為 0 的不完整數據不記
        if avg <= 0 and exit_px <= 0:
            continue
        recs.append({
            "symbol": sym,
            "side": pside,
            "positionAmt": amt,
            "avgPrice": avg,            # 開倉價
            "exitPrice": exit_px,       # 平倉價 (持倉中多為0)
            "leverage": lev,
            "unrealizedProfit": upnl,
            "realizedProfit": rpnl,
            "pnlRatio": pnl_ratio,       # 盈虧比
            "positionValue": pval,       # 總倉位大小
            "liquidationPrice": liq,
            "status": "OPEN",
            "ts": int(time.time() * 1000),
        })

    # 註: 已平倉歷史 (income API) 只有盈虧數字, 沒有開平價
    #     依需求不記錄 (避免不完整開關倉數據)
    #     若未來需要, 改用 orders API 配對開平價後再記

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "bingx-swap",
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
