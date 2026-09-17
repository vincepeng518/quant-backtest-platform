from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.auth import ANON_OWNER, owner_id_for
from app.models.schemas import BacktestConfig, BacktestResultOut, TaskStatus
from app.services.backtest_service import BacktestService
from app.services.data_service import _backtest_tasks


def _owner_from(request: Request) -> str:
    """由 Authorization header 推導 owner（單人站台的穩定識別）。"""
    import os

    bearer = os.getenv("API_BEARER_TOKEN") or ""
    auth = request.headers.get("authorization") or ""
    if bearer and auth.startswith("Bearer "):
        tok = auth.split(" ", 1)[1].strip()
        if tok == bearer:
            return owner_id_for(tok)
    return ANON_OWNER

# Backtests are written by app/services/data_service.py to <repo>/backtests,
# i.e. parents[2] of that module — anchor here so both reader routes agree.
_DATA_SERVICE = __import__("app.services.data_service", fromlist=["__file__"]).__file__
BACKTESTS_DIR = Path(_DATA_SERVICE).resolve().parents[2] / "backtests"

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
svc = BacktestService()


@router.post("/run", status_code=202)
async def run_backtest(config: BacktestConfig, request: Request):
    # Defense-in-depth: sandbox-check custom_code even if not currently exec'd,
    # so a future execution path can't RCE. Mirrors strategy/upload validation.
    if config.strategy.custom_code:
        from app.core.sandbox import check_strategy_code
        ok, err = check_strategy_code(config.strategy.custom_code)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Strategy rejected: {err}")
    # 匿名（未認證）跑的回測必須 ephemeral：不落庫、不進 history。
    ephemeral = bool(getattr(request.state, "ephemeral", False))
    owner = ANON_OWNER if ephemeral else _owner_from(request)
    res = await svc.run(config.model_dump(), owner=owner, ephemeral=ephemeral)
    if isinstance(res, dict) and ephemeral:
        res["ephemeral"] = True
    return res


@router.get("/history")
async def list_history(request: Request):
    import math as _m
    def _j(n):
        """inf/NaN → None(JSON 不安全 float)"""
        try:
            f = float(n)
            return None if (_m.isinf(f) or _m.isnan(f)) else n
        except (TypeError, ValueError):
            return None
    owner = _owner_from(request)
    bd = BACKTESTS_DIR
    if not bd.exists():
        return []
    items = []
    for f in sorted(bd.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        # owner 隔離：舊檔無 owner 欄位 → 視為 legacy，只有持有 token 者可讀。
        file_owner = d.get("owner")
        if file_owner is not None:
            if file_owner != owner:
                continue
        elif owner == ANON_OWNER:
            continue
        m = d.get("metrics", {}) or {}
        cfg = d.get("config", {}) or {}
        strat = cfg.get("strategy_id")
        if not strat and isinstance(cfg.get("strategy"), dict):
            strat = cfg["strategy"].get("template_id")
        items.append({
            "task_id": d.get("task_id"),
            "status": d.get("status"),
            "created_at": d.get("created_at"),
            "strategy": strat,
            "symbol": cfg.get("symbol"),
            "timeframe": cfg.get("timeframe"),
            "sharpe": _j(m.get("sharpe_ratio")),
            "total_trades": _j(m.get("total_trades")),
            "quality_score": _j(m.get("quality_score")),
            "quality_grade": m.get("quality_grade"),
            # T3: 帶入完整 config(供「複製參數」填表單)
            "config": {
                "strategy": cfg.get("strategy") if isinstance(cfg.get("strategy"), dict) else {"template_id": strat},
                "symbol": cfg.get("symbol"),
                "timeframe": cfg.get("timeframe"),
                "start_date": cfg.get("start_date", ""),
                "end_date": cfg.get("end_date", ""),
                "initial_capital": _j(cfg.get("initial_capital", 100000)),
                "commission": _j(cfg.get("commission", 0.001)),
            },
        })
    return items


@router.delete("/history")
async def delete_history(ids: list[str], request: Request):
    """批次刪除歷史回測紀錄(本機檔 + GitHub)。回報刪除結果與失敗。"""
    if not ids:
        return {"deleted": [], "failed": []}
    owner = _owner_from(request)
    bd = BACKTESTS_DIR
    deleted, failed = [], []
    removed_local = []
    for tid in ids:
        fp = bd / f"{tid}.json"
        if fp.exists():
            # owner 隔離：只能刪自己的（舊檔無 owner → legacy 僅認證者可刪）
            try:
                _d = json.loads(fp.read_text())
                _fo = _d.get("owner")
            except Exception:
                _fo = None
            if (_fo is not None and _fo != owner) or (_fo is None and owner == ANON_OWNER):
                failed.append({"task_id": tid, "error": "not found"})
                continue
            try:
                fp.unlink()
                removed_local.append(str(fp))
                deleted.append(tid)
            except Exception as e:
                failed.append({"task_id": tid, "error": f"本地刪除失敗: {str(e)[:100]}"})
        else:
            # 本機沒有但可能在 GitHub → 標記待刪(透過 git_persist 的 _delete)
            removed_local.append(str(bd / f"{tid}.json"))
            deleted.append(tid)
    if removed_local:
        try:
            from app.services.strategy_git import git_persist
            ok, detail = git_persist(removed_local, f"feat(backtest): delete history {len(deleted)}")
            if not ok:
                failed.append({"task_id": "all", "error": f"GitHub 同步失敗: {detail}"})
        except Exception as e:
            failed.append({"task_id": "all", "error": f"GitHub 同步錯誤: {str(e)[:100]}"})
    return {"deleted": deleted, "failed": failed}


@router.get("/status/{task_id}")
async def get_status(task_id: str, request: Request):
    task = _backtest_tasks.get(task_id)
    if task is not None and task.get("owner", ANON_OWNER) != _owner_from(request):
        raise HTTPException(status_code=404, detail="task not found")
    s = svc.get_status(task_id)
    return TaskStatus(**s)


@router.post("/cancel/{task_id}")
async def cancel_backtest(task_id: str, request: Request):
    task = _backtest_tasks.get(task_id)
    if task is not None and task.get("owner", ANON_OWNER) != _owner_from(request):
        raise HTTPException(status_code=404, detail="task not found")
    return svc.cancel(task_id)


def _result_to_out(task_id: str, result, config: dict | None = None) -> BacktestResultOut:
    """Convert an in-memory BacktestResult dataclass to BacktestResultOut.

    The dataclass stores Trade.entry_time/exit_time as pd.Timestamp, which
    pydantic v2 will not auto-coerce to str -> we stringify explicitly.
    Metrics live as flat fields on the dataclass (not a nested dict).
    equity_curve / buy_hold_curve are aligned with `timestamps` and emitted as
    {time, equity} point arrays (frontend charts need a time axis).
    """
    from dataclasses import asdict as _asdict

    def _ts(v):
        return str(v) if v is not None else None

    def _to_unix(v):
        if v is None:
            return None
        try:
            return int(pd.Timestamp(v).timestamp())
        except Exception:
            return None

    r = result
    trades = [
        {
            "entry_time": _ts(t.entry_time),
            "entry_price": t.entry_price,
            "exit_time": _ts(t.exit_time),
            "exit_price": t.exit_price,
            "size": t.size,
            "pnl": t.pnl,
            "pnl_pct": t.pnl_pct,
            "direction": getattr(t, "direction", "long"),
            "exit_reason": getattr(t, "exit_reason", ""),
            "holding_bars": getattr(t, "holding_bars", 0),
        }
        for t in r.trades
    ]
    _ts_list = getattr(r, "timestamps", []) or []
    equity_curve = [
        {"time": _to_unix(ts), "equity": float(eq)}
        for ts, eq in zip(_ts_list, r.equity_curve)
        if _to_unix(ts) is not None
    ]
    buy_hold_curve = [
        {"time": _to_unix(ts), "equity": float(eq)}
        for ts, eq in zip(_ts_list, getattr(r, "buy_hold_curve", []) or [])
        if _to_unix(ts) is not None
    ]
    position_status = getattr(r, "position_status", []) or []

    # ── K 線 + 交易標記 ──
    # 前端 TvBacktestChart 需要 chart_data（OHLCV）才能畫圖、需要 markers 才能
    # 標買賣點。先前 API 沒回這兩個欄位，圖表固定顯示 "No backtest data"。
    chart_data: list[dict] = []
    markers: list[dict] = []
    # 原始 K 線存在 backtester 上（bt.set_data 存進 self.data），
    # 回測結果本身不含 OHLCV，所以從 task 的 backtester 取。
    _task = _backtest_tasks.get(task_id) or {}
    _bt = _task.get("backtester")
    data = getattr(_bt, "data", None) if _bt is not None else None
    if data is not None and len(data) > 0:
        for _, row in data.iterrows():
            ts = _to_unix(row.get("timestamp"))
            if ts is None:
                continue
            try:
                chart_data.append({
                    "time": ts,
                    "timestamp": ts,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume") or 0.0),
                })
            except Exception:
                continue
        # 交易標記：進場買/賣，出場平倉
        for t in r.trades:
            ets = _to_unix(t.entry_time)
            xts = _to_unix(t.exit_time)
            if ets is not None:
                is_long = getattr(t, "direction", "long") == "long"
                markers.append({
                    "time": ets,
                    "position": "belowBar" if is_long else "aboveBar",
                    "color": "#16a34a" if is_long else "#dc2626",
                    "shape": "arrowUp" if is_long else "arrowDown",
                    "text": "買" if is_long else "賣",
                })
            if xts is not None:
                markers.append({
                    "time": xts,
                    "position": "inBar",
                    "color": "#64748b",
                    "shape": "circle",
                    "text": "平",
                })
        markers.sort(key=lambda m: m["time"])
    # ── Quality score 兜底: 若 backtester 未計算 (舊代碼), API 層補算 ──
    q_score = getattr(r, "quality_score", None)
    q_grade = getattr(r, "quality_grade", None)
    q_breakdown = getattr(r, "quality_breakdown", None)
    # 0.0 也視為未計算 (dataclass 預設值), 除非真的 0 筆交易
    if q_score is None or (q_score == 0.0 and r.total_trades > 0):
        try:
            from engine.backtester import compute_quality_score
            _w = [t.pnl for t in r.trades if t.pnl is not None and t.pnl > 0]
            _l = [t.pnl for t in r.trades if t.pnl is not None and t.pnl < 0]
            _pf = (abs(sum(_w) / sum(_l)) if _l
                   else (999.0 if _w else 0.0))
            q_score, q_grade, q_breakdown = compute_quality_score(
                sharpe=r.sharpe_ratio,
                profit_factor=_pf,
                win_rate=r.win_rate,
                max_drawdown_pct=r.max_drawdown_pct,
                total_trades=r.total_trades,
            )
        except Exception:
            from engine.backtester import _EMPTY_BREAKDOWN
            q_score, q_grade, q_breakdown = 0.0, "F", {**_EMPTY_BREAKDOWN, "penalty_reason": "兜底計算異常"}
    return BacktestResultOut(
        task_id=task_id,
        status="completed",
        config=config or {},
        metrics={
            "total_trades": r.total_trades,
            "winning_trades": r.winning_trades,
            "losing_trades": r.losing_trades,
            "win_rate": r.win_rate,
            "total_return_pct": r.total_return_pct,
            "max_drawdown": r.max_drawdown,
            "max_drawdown_pct": r.max_drawdown_pct,
            "sharpe_ratio": r.sharpe_ratio,
            "sortino_ratio": r.sortino_ratio,
            "profit_factor": r.profit_factor,
            "avg_trade": r.avg_trade,
            "avg_winner": r.avg_winner,
            "avg_loser": r.avg_loser,
            "net_profit": float(r.total_pnl),
            "largest_loss": r.largest_loss,
            "largest_loss_pct": r.largest_loss_pct,
            "largest_win": r.largest_win,
            "win_loss_ratio": r.win_loss_ratio,
            "expectancy": r.expectancy,
            "annual_return_pct": r.annual_return_pct,
            "calmar_ratio": r.calmar_ratio,
            "avg_holding_bars": r.avg_holding_bars,
            "trade_freq": r.trade_freq,
            # Long/Short split — 必須顯式帶上，否則 MetricsOut 宣告的欄位會
            # 靜默退回預設 0（AGENTS.md 記載的 Pydantic 陷阱），
            # 造成前端「多 0 / 空 0」但 trades 裡明明有 11 筆的長短倉。
            "long_trades": r.long_trades,
            "short_trades": r.short_trades,
            "long_win_rate": r.long_win_rate,
            "short_win_rate": r.short_win_rate,
            "long_pnl": r.long_pnl,
            "short_pnl": r.short_pnl,
            "long_expectancy": r.long_expectancy,
            "short_expectancy": r.short_expectancy,
            "long_profit_factor": r.long_profit_factor,
            "short_profit_factor": r.short_profit_factor,
            "quality_score": q_score,
            "quality_grade": q_grade,
            "quality_breakdown": q_breakdown or {},
        },
        equity_curve=equity_curve,
        buy_hold_equity=buy_hold_curve,
        trades=trades,
        position_status=position_status,
        chart_data=chart_data,
        markers=markers,
    )


@router.get("/results/{task_id}", response_model=BacktestResultOut)
async def get_results(task_id: str, request: Request):
    owner = _owner_from(request)
    task = _backtest_tasks.get(task_id)
    if task and task.get("result") is not None:
        # owner 隔離：非本人 task → 404（不洩漏存在性）
        if task.get("owner", ANON_OWNER) != owner:
            raise HTTPException(status_code=404, detail="task not found")
        return _result_to_out(task_id, task["result"], task.get("config"))
    bd = BACKTESTS_DIR
    fp = bd / f"{task_id}.json"
    if fp.exists():
        d = json.loads(fp.read_text())
        # owner 隔離：舊檔無 owner 欄位 → legacy，只有認證者可讀
        file_owner = d.get("owner")
        if (file_owner is not None and file_owner != owner) or (
            file_owner is None and owner == ANON_OWNER
        ):
            raise HTTPException(status_code=404, detail="task not found")
        metrics = dict(d.get("metrics", {}))
        # 兜底: 舊 JSON 無 quality_score 時補算
        m_qs = metrics.get("quality_score")
        if m_qs is None or (m_qs == 0.0 and (metrics.get("total_trades") or 0) > 0):
            try:
                from engine.backtester import compute_quality_score
                trades = d.get("trades", [])
                _w = [t.get("pnl") for t in trades if t.get("pnl") is not None and t.get("pnl") > 0]
                _l = [t.get("pnl") for t in trades if t.get("pnl") is not None and t.get("pnl") < 0]
                _pf = (abs(sum(_w) / sum(_l)) if _l
                       else (999.0 if _w else 0.0))
                qs, qg, qbrk = compute_quality_score(
                    sharpe=metrics.get("sharpe_ratio") or 0,
                    profit_factor=_pf,
                    win_rate=metrics.get("win_rate") or 0,
                    max_drawdown_pct=metrics.get("max_drawdown_pct") or 0,
                    total_trades=metrics.get("total_trades") or 0,
                )
                metrics["quality_score"] = qs
                metrics["quality_grade"] = qg
                metrics["quality_breakdown"] = qbrk
            except Exception:
                pass
        # 兜底: 舊 JSON equity_curve 可能是 float[]（無 time key），轉成 dict 格式
        _ec_raw = d.get("equity_curve", [])
        if _ec_raw and isinstance(_ec_raw[0], (int, float)):
            _ts = d.get("timestamps", [])
            _ec = []
            for i, v in enumerate(_ec_raw):
                _tv = _ts[i] if i < len(_ts) and _ts[i] else None
                _tu = None
                if _tv is not None:
                    try:
                        _tu = int(pd.Timestamp(_tv).timestamp())
                    except Exception:
                        _tu = None
                _ec.append({"time": (_tu if _tu is not None else i), "equity": float(v)})
        else:
            _ec = _ec_raw

        # ── K 線 + markers 兜底（舊 JSON 沒有這兩個欄位）──
        # 從 /history 點進來的是這條路徑；沒有 chart_data 圖表就是 No backtest data。
        _chart = d.get("chart_data") or []
        _markers = d.get("markers") or []
        if not _chart:
            cfg = d.get("config", {}) or {}
            try:
                data = await svc.data_service.get_ohlcv(
                    symbol=cfg.get("symbol", ""),
                    timeframe=cfg.get("timeframe", "1h"),
                    start_date=cfg.get("start_date", ""),
                    end_date=cfg.get("end_date", ""),
                    source=cfg.get("source") or "bingx",
                )
                if data is not None and len(data) > 0:
                    for _, row in data.iterrows():
                        try:
                            _u = int(pd.Timestamp(row["timestamp"]).timestamp())
                        except Exception:
                            continue
                        _chart.append({
                            "time": _u, "timestamp": _u,
                            "open": float(row["open"]), "high": float(row["high"]),
                            "low": float(row["low"]), "close": float(row["close"]),
                            "volume": float(row.get("volume") or 0.0),
                        })
            except Exception:
                _chart = []
        if not _markers and d.get("trades"):
            def _mk_ts(v):
                try:
                    _t = pd.Timestamp(v)
                except Exception:
                    return None
                if _t is None or str(_t) == "NaT":
                    return None
                try:
                    return int(_t.timestamp())
                except Exception:
                    return None
            for t in d["trades"]:
                _e, _x = _mk_ts(t.get("entry_time")), _mk_ts(t.get("exit_time"))
                _long = (t.get("direction") or "long") == "long"
                if _e is not None:
                    _markers.append({"time": _e,
                                     "position": "belowBar" if _long else "aboveBar",
                                     "color": "#16a34a" if _long else "#dc2626",
                                     "shape": "arrowUp" if _long else "arrowDown",
                                     "text": "買" if _long else "賣"})
                if _x is not None:
                    _markers.append({"time": _x, "position": "inBar",
                                     "color": "#64748b", "shape": "circle", "text": "平"})
            _markers.sort(key=lambda m: m["time"])

        return BacktestResultOut(
            task_id=task_id,
            status=d.get("status", "completed"),
            config=d.get("config", {}),
            metrics=metrics,
            equity_curve=_ec,
            trades=d.get("trades", []),
            chart_data=_chart,
            markers=_markers,
        )
    raise HTTPException(status_code=404, detail="task not found")


class PushNotionRequest(BaseModel):
    task_id: str
    symbol: str = ""
    strategy: str = ""
    timeframe: str = ""


@router.post("/push-notion")
async def push_notion(req: PushNotionRequest):
    """推送回測結果到 Notion ATM 頁。若未設 NOTION_ATM_PAGE_ID 則靜默跳過。"""
    from app.services.notion_service import push as push_notion_svc
    fp = BACKTESTS_DIR / f"{req.task_id}.json"
    if not fp.exists():
        raise HTTPException(status_code=404, detail="task not found")
    d = json.loads(fp.read_text())
    ok = push_notion_svc(
        {"metrics": d.get("metrics", {}), "trades": d.get("trades", [])},
        req.symbol or d.get("config", {}).get("symbol", "?"),
        req.strategy or d.get("config", {}).get("strategy", {}).get("template_id", "?"),
        req.timeframe or d.get("config", {}).get("timeframe", "?"),
    )
    return {"ok": ok, "notion_configured": bool(os.getenv("NOTION_BACKTEST_PAGE_ID"))}
