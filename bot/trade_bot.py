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
    last_err = None
    for attempt in range(3):
        try:
            r = _requests.get(url, headers={
                "X-BX-APIKEY": os.environ.get("BINGX_API_KEY", ""),
                "X-SOURCE-KEY": "BX-AI-SKILL",
            }, timeout=15)
            if r.status_code == 429:
                # 限流: 退避後重試
                wait = 2 * (attempt + 1)
                logger.warning("BingX 429 rate limit on %s, retry in %ss", path, wait)
                time.sleep(wait)
                last_err = "429"
                continue
            return r.json()
        except Exception as e:  # noqa
            last_err = e
            logger.warning("private call %s err (attempt %d): %s", path, attempt + 1, e)
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
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
    # 商品/股票/股指: NC{CO|SK|SI}[數字]<NAME>2USD-USDT → NAME (前導數字如 1OILWTI 去掉)
    m = re.match(r"^NC(CO|SK|SI)\d*(.+?)2USD-USDT$", s)
    if m:
        return m.group(2)
    # TradFi 變體: NC<NAME>-USDT → NAME (無 2USD 後綴, 例 NCOILWTI-USDT → OILWTI)
    m = re.match(r"^NC(\w+)-USDT$", s)
    if m:
        return m.group(1)
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


def fetch_order_history(limit: int = 200) -> list:
    """私有 allOrders: 歷史成交 (含開平價, ccxt 無法逐 symbol 掃歷史)。
    分頁拉取: BingX 單次最多 100 筆, 用 id 游標往回翻頁, 直到達 limit 或無更多。
    """
    all_orders: list = []
    cursor_id = None
    page = 0
    while len(all_orders) < limit and page < 50:
        params = {"limit": min(100, limit - len(all_orders))}
        if cursor_id is not None:
            params["idLessThan"] = cursor_id  # BingX 分頁: 上一頁最後一筆 id
        try:
            d = _call_private("/openApi/swap/v2/trade/allOrders", params)
            data = d.get("data", {})
            batch = data.get("orders", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            if not batch:
                break
            all_orders.extend(batch)
            cursor_id = batch[-1].get("id")  # 下一頁游標
            page += 1
        except Exception as e:  # noqa
            logger.warning("order history err: %s", e)
            break
    return all_orders[:limit]


def build_snapshot() -> dict:
    """組合一次快照: 當前持倉 (ccxt) + 歷史成交 (私有 allOrders)。
    只記有開平價的完整數據 (過濾無價格的)。"""
    positions = fetch_positions()
    orders = fetch_order_history(1000)

    recs = []
    MAX_SAFE_LEV = 20
    # 1) 當前持倉 (ccxt, status=OPEN)
    for p in positions:
        sym = simplify_symbol(p.get("symbol"))
        pside = p.get("positionSide")  # LONG/SHORT
        avg = float(p.get("avgPrice", 0) or 0)
        amt = float(p.get("positionAmt", 0) or 0)
        lev = float(p.get("leverage", 0) or 0)
        if lev > MAX_SAFE_LEV:
            # 高槓桿持倉: 不阻止, 但標記穿倉風險
            logger.warning("高槓桿持倉 %s %sx — 穿倉風險, 建議降到 %dx 以下", sym, lev, MAX_SAFE_LEV)
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

    # 2) 歷史成交 (私有 allOrders) -> 配對成 round-trip (開倉+平倉)
    #    BingX 每筆 order 只有單邊價; 一筆完整交易 = 開倉單 + 平倉單
    #    配對: 同 symbol+positionSide, 按時間排序, 開倉方向單入棧, 平倉方向單出棧配對
    fees_total = 0.0
    # 過濾有效成交單
    valid = []
    for o in orders:
        if o.get("status") != "FILLED":
            continue
        avg = float(o.get("avgPrice", 0) or 0)
        if avg <= 0:
            continue
        valid.append(o)

    # 分組 (symbol, positionSide)
    groups: dict = {}
    for o in valid:
        key = (simplify_symbol(o.get("symbol")), o.get("positionSide"))
        groups.setdefault(key, []).append(o)

    recs_closed: list = []
    for (sym, pside), grp in groups.items():
        # 按時間升序
        grp.sort(key=lambda x: int(x.get("time", 0) or 0))
        # 開倉方向: LONG->BUY, SHORT->SELL; 平倉方向相反
        open_side = "BUY" if pside == "LONG" else "SELL"
        stack: list = []
        for o in grp:
            oside = (o.get("side") or "").upper()
            avg = float(o.get("avgPrice", 0) or 0)
            rpnl = float(o.get("profit", 0) or 0)
            fees_total += float(o.get("commission", 0) or 0)
            if oside == open_side:
                # 開倉單: 入棧 (攜帶開倉價/時間/數量)
                stack.append({
                    "avgPrice": avg,
                    "time": int(o.get("time", 0) or 0),
                    "qty": float(o.get("executedQty", 0) or 0),
                })
            else:
                # 平倉單: 與棧頂開倉單配對 (無開倉則單獨記一筆 FILLED)
                entry = stack.pop() if stack else None
                entry_price = entry["avgPrice"] if entry else avg
                recs_closed.append({
                    "symbol": sym,
                    "side": pside,
                    "positionAmt": float(o.get("executedQty", 0) or 0),
                    "avgPrice": entry_price,       # 開倉價 (來自開倉單)
                    "exitPrice": avg,              # 平倉價 (來自平倉單)
                    "leverage": _parse_lev(o.get("leverage")),
                    "unrealizedProfit": 0.0,
                    "realizedProfit": rpnl,
                    "pnlRatio": 0.0,
                    "positionValue": float(o.get("cumQuote", 0) or 0),
                    "liquidationPrice": 0.0,
                    "status": "CLOSED",
                    "ts": int(o.get("time", 0) or 0),
                })

    recs.extend(recs_closed)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "bingx-ccxt+orders",
        "repo": REPO,
        "count": len(recs),
        "fees_total": round(fees_total, 4),
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
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return True, "pushed" if r.status == 201 or r.status == 200 else str(r.status)
        except Exception as e:  # noqa
            last_err = e
            if attempt < 2:
                time.sleep(2 * (attempt + 1))  # 指數退避
    return False, str(last_err)[:200] if last_err else "unknown"


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
