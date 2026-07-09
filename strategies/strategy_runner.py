"""
策略執行器
讓使用者輸入 Python 程式碼，產生進出場訊號
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any


def execute_user_strategy(
    code: str, df: pd.DataFrame, params: Dict[str, Any]
) -> Tuple[pd.Series, pd.Series, str]:
    """
    執行使用者策略代碼
    code: Python 程式碼（需定義 generate_signals(df, params) 函數，回傳 (entries, exits)）
    df: OHLCV 資料
    params: 參數 dict
    回傳: (entries Series, exits Series, error_message)
    """
    if not code.strip():
        empty = pd.Series(False, index=df.index)
        return empty, empty, "請輸入策略代碼"

    # 安全沙箱：限制可用的內建函數
    safe_builtins = {
        "len": len, "range": range, "min": min, "max": max,
        "abs": abs, "round": round, "sum": sum,
        "True": True, "False": False, "None": None,
        "list": list, "dict": dict, "tuple": tuple, "set": set,
        "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    }

    namespace = {
        "__builtins__": safe_builtins,
        "pd": pd,
        "np": np,
        "pandas": pd,
        "numpy": np,
        "params": params,
    }

    try:
        exec(code, namespace)
        if "generate_signals" not in namespace:
            return (
                pd.Series(False, index=df.index),
                pd.Series(False, index=df.index),
                "❌ 找不到函數 'generate_signals'。請定義：def generate_signals(df, params):\n    return entries, exits",
            )

        entries, exits = namespace["generate_signals"](df.copy(), params)

        # 驗證回傳型別
        if not isinstance(entries, pd.Series) or not isinstance(exits, pd.Series):
            return (
                pd.Series(False, index=df.index),
                pd.Series(False, index=df.index),
                "❌ generate_signals 必須回傳兩個 pandas Series: (entries, exits)",
            )

        # 對齊 index
        entries = entries.reindex(df.index, fill_value=False).astype(bool)
        exits = exits.reindex(df.index, fill_value=False).astype(bool)

        return entries, exits, ""

    except SyntaxError as e:
        return (
            pd.Series(False, index=df.index),
            pd.Series(False, index=df.index),
            f"❌ 語法錯誤: {e}",
        )
    except Exception as e:
        return (
            pd.Series(False, index=df.index),
            pd.Series(False, index=df.index),
            f"❌ 執行錯誤: {type(e).__name__}: {e}",
        )


# === 預設策略範本 ===

STRATEGY_TEMPLATES = {
    "均線交叉 (SMA Crossover)": '''# 均線交叉策略
# 當快線向上穿越慢線時進場（做多）
# 當快線向下穿越慢線時出場

def generate_signals(df, params):
    fast = params.get("fast_period", 20)
    slow = params.get("slow_period", 50)

    df["sma_fast"] = df["close"].rolling(fast).mean()
    df["sma_slow"] = df["close"].rolling(slow).mean()

    # 進場：快線 > 慢線（且前一刻 ≤ 慢線，避免重複進場）
    entries = (df["sma_fast"] > df["sma_slow"]) & (df["sma_fast"].shift(1) <= df["sma_slow"].shift(1))
    exits = (df["sma_fast"] < df["sma_slow"]) & (df["sma_fast"].shift(1) >= df["sma_slow"].shift(1))

    return entries.fillna(False), exits.fillna(False)
''',

    "RSI 超買超賣": '''# RSI 策略
# RSI < 進場門檻 → 進場做多
# RSI > 出場門檻 → 出場

def generate_signals(df, params):
    period = params.get("rsi_period", 14)
    entry_level = params.get("entry_level", 30)
    exit_level = params.get("exit_level", 70)

    # 計算 RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    entries = (df["rsi"] < entry_level) & (df["rsi"].shift(1) >= entry_level)
    exits = (df["rsi"] > exit_level) & (df["rsi"].shift(1) <= exit_level)

    return entries.fillna(False), exits.fillna(False)
''',

    "布林通道 (Bollinger Bands)": '''# 布林通道均值回歸策略
# 價格跌破下軌 → 進場做多（預期回歸中軌）
# 價格漲破中軌 → 出場

def generate_signals(df, params):
    period = params.get("bb_period", 20)
    num_std = params.get("num_std", 2.0)

    df["bb_mid"] = df["close"].rolling(period).mean()
    df["bb_std"] = df["close"].rolling(period).std()
    df["bb_upper"] = df["bb_mid"] + num_std * df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - num_std * df["bb_std"]

    # 進場：價格從下方穿越下軌
    entries = (df["close"] < df["bb_lower"]) & (df["close"].shift(1) >= df["bb_lower"].shift(1))
    # 出場：價格回到中軌
    exits = (df["close"] > df["bb_mid"]) & (df["close"].shift(1) <= df["bb_mid"].shift(1))

    return entries.fillna(False), exits.fillna(False)
''',

    "MACD 交叉": '''# MACD 交叉策略
# MACD 線向上穿越訊號線 → 進場
# MACD 線向下穿越訊號線 → 出場

def generate_signals(df, params):
    fast = params.get("fast", 12)
    slow = params.get("slow", 26)
    signal = params.get("signal", 9)

    df["ema_fast"] = df["close"].ewm(span=fast, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=slow, adjust=False).mean()
    df["macd"] = df["ema_fast"] - df["ema_slow"]
    df["macd_signal"] = df["macd"].ewm(span=signal, adjust=False).mean()

    entries = (df["macd"] > df["macd_signal"]) & (df["macd"].shift(1) <= df["macd_signal"].shift(1))
    exits = (df["macd"] < df["macd_signal"]) & (df["macd"].shift(1) >= df["macd_signal"].shift(1))

    return entries.fillna(False), exits.fillna(False)
''',

    "網格交易 (Grid Trading)": '''# 簡化版網格交易
# 價格每跌 X% 買入，每漲 Y% 賣出
# 注意：這是簡化版，不處理部位大小遞增

def generate_signals(df, params):
    grid_size = params.get("grid_size", 0.02)  # 2% 網格

    # 計算相對最近高點的跌幅
    lookback = params.get("lookback", 20)
    df["recent_high"] = df["close"].rolling(lookback).max()
    df["drawdown"] = (df["close"] - df["recent_high"]) / df["recent_high"]

    # 每跌 N 個網格買一次
    n_grids_below = (df["drawdown"] / -grid_size).astype(int)
    prev_n = n_grids_below.shift(1).fillna(0)
    entries = (n_grids_below > prev_n)

    # 漲回前一個網格就賣
    prev_n_exit = n_grids_below.shift(1).fillna(0)
    exits = (n_grids_below < prev_n_exit)

    return entries.fillna(False), exits.fillna(False)
''',

    "海龜交易 (Turtle)": '''# 簡化版海龜交易策略
# 突破 N 日高點買入，跌破 M 日低點賣出

def generate_signals(df, params):
    entry_break = params.get("entry_break", 20)
    exit_break = params.get("exit_break", 10)

    df["high_break"] = df["high"].rolling(entry_break).max().shift(1)
    df["low_break"] = df["low"].rolling(exit_break).min().shift(1)

    entries = df["close"] > df["high_break"]
    exits = df["close"] < df["low_break"]

    return entries.fillna(False), exits.fillna(False)
''',
}


def get_template(name: str) -> str:
    """取得策略範本"""
    return STRATEGY_TEMPLATES.get(name, "")


def list_templates() -> list:
    """列出所有可用的策略範本"""
    return list(STRATEGY_TEMPLATES.keys())
