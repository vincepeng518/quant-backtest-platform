"""app/services/validation.py — 金融輸入數值防護(邊界限制,純新增,不碰回測核心)。

攔截非法數值:NaN / Infinity / 負或零的初始資金 / 超出合理範圍的參數。
Pydantic ge/le/gt 對 NaN 不攔(NaN 比較皆 false),故在此統一補驗證,所有回測入口共用。

回傳 error 字串(非空=攔截)或 None。
"""
from __future__ import annotations

import math
from typing import Any

# 合理範圍(防極端佔用/溢出):初始資金 1..1e12,commission/slippage 0..1,槓桿 1..200
CAPITAL_MIN, CAPITAL_MAX = 1.0, 1e12
FEE_MIN, FEE_MAX = 0.0, 1.0
LEV_MIN, LEV_MAX = 1.0, 200.0


def _bad(v: Any, name: str) -> str | None:
    """檢查單一數值:回 error 或 None。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return f"{name}=<{v!r}> 非數值"
    if math.isnan(f):
        return f"{name}=NaN 非法數值"
    if math.isinf(f):
        return f"{name}=Infinity 非法數值"
    return None


def validate_financial_inputs(config: dict[str, Any]) -> str | None:
    """對回測/優化 config 做數值邊界防護。回 error 或 None。"""
    # 初始資金必須為正有限
    cap = _bad(config.get("initial_capital", 100000), "initial_capital")
    if cap:
        return cap
    cap_f = float(config.get("initial_capital", 100000))
    if not (CAPITAL_MIN <= cap_f <= CAPITAL_MAX):
        return f"initial_capital={cap_f} 超出允許範圍[{CAPITAL_MIN},{CAPITAL_MAX}]"

    for fee_key in ("commission", "slippage"):
        if fee_key in config:
            e = _bad(config.get(fee_key), fee_key)
            if e:
                return e
            v = float(config[fee_key])
            if not (FEE_MIN <= v <= FEE_MAX):
                return f"{fee_key}={v} 超出允許範圍[{FEE_MIN},{FEE_MAX}]"

    # 策略參數:每個數值參數須為有限(範圍由策略模板定義,此處只擋 NaN/Inf)
    params = config.get("params") or {}
    for k, v in params.items():
        if isinstance(v, (int, float, str)):
            e = _bad(v, f"params.{k}")
            if e:
                return e
    return None
