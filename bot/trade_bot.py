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

# ccxt 統一交易所介面 (替代 BingX 私有 HMAC 簽名)
try:
    import ccxt
except Exception as e:  # noqa
    logger.warning("ccxt import failed: %s", e)
    ccxt = None

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


def _ccxt_sym(raw: str | None) -> str | None:
    """ccxt 格式 ETH/USDT:USDT -> ETH-USDT (統一介面輸出)"""
    if not raw:
        return raw
    return raw.replace("/", "-").replace(":USDT", "").replace(":USDC", "")


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
            sym = _ccxt_sym(p.get("symbol"))
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


def build_snapshot() -> dict:
    """組合一次快照: 持倉 (ccxt 抓取, 只含有開倉價的完整數據)。"""
    positions = fetch_positions()

    # symbol 簡化映射 (BingX 長名 -> 好讀)
    SYMBOL_MAP = {
        "NCCOGOLD2USD-USDT": "GOLD-USDT",
    }

    recs = []
    for p in positions:
        sym = SYMBOL_MAP.get(p.get("symbol"), p.get("symbol"))
        pside = p.get("positionSide")  # LONG/SHORT
        avg = float(p.get("avgPrice", 0) or 0)
        lev = float(p.get("leverage", 0) or 0)
        upnl = float(p.get("unrealizedProfit", 0) or 0)
        rpnl = float(p.get("realisedProfit", 0) or 0)
        pnl_ratio = float(p.get("pnlRatio", 0) or 0)
        pval = float(p.get("positionValue", 0) or 0)
        liq = float(p.get("liquidationPrice", 0) or 0)
        amt = float(p.get("positionAmt", 0) or 0)
        # 持倉中尚未平倉: exit price 強制 0 (避免偽造平倉價)
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

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "bingx-ccxt",
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
