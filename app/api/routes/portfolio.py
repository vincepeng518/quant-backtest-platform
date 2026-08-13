"""app/api/routes/portfolio.py — 多標的組合對沖回測 API。

POST /api/portfolio/run  body:
  {
    "symbols": ["BTC/USDT","ETH/USDT"],
    "strategy": {"template_id":"ma_cross","params":{...}},
    "timeframe":"1d","start_date":"","end_date":"",
    "initial_capital":100000,"commission":0.001,"source":"bingx",
    "weights": {"BTC/USDT":0.5,"ETH/USDT":0.5}   # 可選,預設等權
  }
回傳: correlation_matrix / portfolio_metrics / hedge_report / individual / portfolio_equity。
異常計算(異常負值/非有限) → status:"error" + error 詳細(不吞)。
"""
from __future__ import annotations
import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class PortfolioRunRequest(BaseModel):
    symbols: list[str] = Field(min_length=2, max_length=10)
    strategy: dict = Field(default_factory=lambda: {"template_id": "ma_cross", "params": {}})
    timeframe: str = "1d"
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = Field(default=100_000.0, gt=0.0, le=1e12)
    commission: float = Field(default=0.001, ge=0.0, le=1.0)
    source: str = ""
    weights: dict[str, float] | None = None

    @field_validator("initial_capital")
    @classmethod
    def _cap_finite(cls, v):
        if not math.isfinite(v):
            raise ValueError("initial_capital must be finite")
        return v

    @field_validator("timeframe")
    @classmethod
    def _tf(cls, v):
        import re
        if not re.fullmatch(r"\d{1,5}[smhdwM]", v):
            raise ValueError("invalid timeframe")
        return v

    @field_validator("symbols")
    @classmethod
    def _syms(cls, v):
        if len(set(v)) < 2:
            raise ValueError("需要至少 2 個不同標的")
        return v


@router.post("/run")
async def run_portfolio(req: PortfolioRunRequest):
    from fastapi.responses import JSONResponse
    from app.services.portfolio_service import run_portfolio_backtest
    try:
        result = await run_portfolio_backtest(req.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        result = {"status": "error", "error": f"組合回測執行失敗: {e}"}
    # 明確 no-store, 防止 Vercel/瀏覽器對 POST 響應做快取(舊instance值殘留問題)
    return JSONResponse(content=result, headers={
        "Cache-Control": "no-store, max-age=0, must-revalidate",
        "Pragma": "no-cache",
    })
