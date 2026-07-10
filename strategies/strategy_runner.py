"""
策略執行器
讓使用者輸入 Python 程式碼，產生進出場訊號
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any


def execute_user_strategy(
    code: str, df: pd.DataFrame, params: Dict[str, Any]
) -> Tuple[pd.Series, pd.Series, str, pd.Series, pd.Series, pd.Series, pd.Series]:
    # 自動處理配對交易資料：若 df 沒有 'close' 但有兩個 _close 欄位，加 'close' 別名
    if "close" not in df.columns:
        close_cols = [c for c in df.columns if c.endswith("_close")]
        if len(close_cols) >= 2:
            # 預設用第一個標的的 close（例如 BTC/USDT_close）
            df = df.copy()
            df["close"] = df[close_cols[0]]
        elif len(close_cols) == 1:
            df = df.copy()
            df["close"] = df[close_cols[0]]
    """
    執行使用者策略代碼

    支援兩種策略回傳格式：
    1. 標準格式（向後兼容）: (entries, exits)
       - 在 long / short 模式下正常運作
    2. 雙向格式: (long_entries, long_exits, short_entries, short_exits)
       - 在 long_short 模式下可同時跑多空

    回傳 7 個元素:
        entries, exits, error_msg,
        long_entries, long_exits, short_entries, short_exits
    """
    if not code.strip():
        empty = pd.Series(False, index=df.index)
        return empty, empty, "請輸入策略代碼", empty, empty, empty, empty

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
            empty = pd.Series(False, index=df.index)
            return (
                empty, empty,
                "❌ 找不到函數 'generate_signals'。請定義：def generate_signals(df, params):\n    return entries, exits\n    # 雙向模式：\n    # return long_entries, long_exits, short_entries, short_exits",
                empty, empty, empty, empty
            )

        result = namespace["generate_signals"](df.copy(), params)

        empty = pd.Series(False, index=df.index)

        # 判斷回傳格式
        if isinstance(result, tuple) and len(result) == 4:
            # 雙向格式: (long_entries, long_exits, short_entries, short_exits)
            long_entries, long_exits, short_entries, short_exits = result

            for name, s in [("long_entries", long_entries), ("long_exits", long_exits),
                             ("short_entries", short_entries), ("short_exits", short_exits)]:
                if not isinstance(s, pd.Series):
                    return (
                        empty, empty,
                        f"❌ {name} 必須是 pandas Series",
                        empty, empty, empty, empty
                    )

            long_entries = long_entries.reindex(df.index, fill_value=False).astype(bool)
            long_exits = long_exits.reindex(df.index, fill_value=False).astype(bool)
            short_entries = short_entries.reindex(df.index, fill_value=False).astype(bool)
            short_exits = short_exits.reindex(df.index, fill_value=False).astype(bool)

            # 對於單向模式，entries/exits 用 long 的（向後兼容）
            return long_entries, long_exits, "", long_entries, long_exits, short_entries, short_exits

        elif isinstance(result, tuple) and len(result) == 2:
            # 標準格式: (entries, exits)
            entries, exits = result

            if not isinstance(entries, pd.Series) or not isinstance(exits, pd.Series):
                return (
                    empty, empty,
                    "❌ generate_signals 必須回傳 (entries, exits) 或 (long_entries, long_exits, short_entries, short_exits)",
                    empty, empty, empty, empty
                )

            entries = entries.reindex(df.index, fill_value=False).astype(bool)
            exits = exits.reindex(df.index, fill_value=False).astype(bool)

            # 雙向訊號設為空（單向模式不用）
            return entries, exits, "", entries, exits, empty, empty
        else:
            return (
                empty, empty,
                "❌ generate_signals 必須回傳 (entries, exits) 或 (long_entries, long_exits, short_entries, short_exits) 共 2 或 4 個 Series",
                empty, empty, empty, empty
            )

    except (SyntaxError, IndentationError, ValueError, TypeError) as e:
        empty = pd.Series(False, index=df.index)
        return (
            empty, empty,
            f"❌ 語法錯誤: {e}",
            empty, empty, empty, empty
        )
    except RecursionError as e:
        empty = pd.Series(False, index=df.index)
        return (
            empty, empty,
            f"❌ 遞迴錯誤: 策略可能有無限遞迴 ({e})",
            empty, empty, empty, empty
        )
    except MemoryError as e:
        empty = pd.Series(False, index=df.index)
        return (
            empty, empty,
            f"❌ 記憶體錯誤: 資料量可能過大 ({e})",
            empty, empty, empty, empty
        )
    except Exception as e:
        empty = pd.Series(False, index=df.index)
        return (
            empty, empty,
            f"❌ 執行錯誤: {type(e).__name__}: {e}",
            empty, empty, empty, empty
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

    entries = (df["close"] < df["bb_lower"]) & (df["close"].shift(1) >= df["bb_lower"].shift(1))
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

def generate_signals(df, params):
    grid_size = params.get("grid_size", 0.02)  # 2% 網格
    lookback = params.get("lookback", 20)

    df["recent_high"] = df["close"].rolling(lookback).max()
    df["drawdown"] = (df["close"] - df["recent_high"]) / df["recent_high"]

    n_grids_below = (df["drawdown"] / -grid_size).astype(int)
    prev_n = n_grids_below.shift(1).fillna(0)
    entries = (n_grids_below > prev_n)
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

    "KDJ 隨機指標": '''# KDJ 隨機指標策略
# K 線由下向上穿越 D 線 → 進場
# K 線由上向下穿越 D 線 → 出場
# J 值 < 0 超賣、> 100 超買

def generate_signals(df, params):
    n = params.get("n", 9)
    m1 = params.get("m1", 3)
    m2 = params.get("m2", 3)

    low_n = df["low"].rolling(n).min()
    high_n = df["high"].rolling(n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n) * 100

    df["k"] = rsv.ewm(alpha=1/m1, adjust=False).mean()
    df["d"] = df["k"].ewm(alpha=1/m2, adjust=False).mean()
    df["j"] = 3 * df["k"] - 2 * df["d"]

    entries = (df["k"] > df["d"]) & (df["k"].shift(1) <= df["d"].shift(1))
    exits = (df["k"] < df["d"]) & (df["k"].shift(1) >= df["d"].shift(1))

    return entries.fillna(False), exits.fillna(False)
''',

    "CCI 順勢指標": '''# CCI (Commodity Channel Index) 策略
# CCI < -100 超賣 → 進場做多
# CCI > +100 超買 → 出場

def generate_signals(df, params):
    period = params.get("cci_period", 20)
    entry_level = params.get("entry_level", -100)
    exit_level = params.get("exit_level", 100)

    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    df["cci"] = (tp - sma) / (0.015 * mad)

    entries = (df["cci"] < entry_level) & (df["cci"].shift(1) >= entry_level)
    exits = (df["cci"] > exit_level) & (df["cci"].shift(1) <= exit_level)

    return entries.fillna(False), exits.fillna(False)
''',

    "Donchian Channels 突破": '''# Donchian Channels 突破策略
# 突破 N 日新高買入
# 跌破 M 日新低賣出

def generate_signals(df, params):
    entry_n = params.get("entry_n", 20)
    exit_n = params.get("exit_n", 10)

    df["upper"] = df["high"].rolling(entry_n).max().shift(1)
    df["lower"] = df["low"].rolling(exit_n).min().shift(1)

    entries = df["close"] > df["upper"]
    exits = df["close"] < df["lower"]

    return entries.fillna(False), exits.fillna(False)
''',

    "三重 EMA (TEMA)": '''# 三重 EMA 策略
# 三條 EMA 多空排列時進場，反轉時出場

def generate_signals(df, params):
    e1 = params.get("ema1", 5)
    e2 = params.get("ema2", 20)
    e3 = params.get("ema3", 50)

    df["ema1"] = df["close"].ewm(span=e1, adjust=False).mean()
    df["ema2"] = df["close"].ewm(span=e2, adjust=False).mean()
    df["ema3"] = df["close"].ewm(span=e3, adjust=False).mean()

    # 多頭排列
    bull = (df["ema1"] > df["ema2"]) & (df["ema2"] > df["ema3"])
    bear = (df["ema1"] < df["ema2"]) & (df["ema2"] < df["ema3"])

    entries = bull & (~bull.shift(1).fillna(False))
    exits = bear & (~bear.shift(1).fillna(False))

    return entries.fillna(False), exits.fillna(False)
''',

    "VWAP 偏離策略": '''# VWAP 偏離均值回歸
# 價格跌破 VWAP 一定倍數標準差 → 進場
# 價格回到 VWAP → 出場

def generate_signals(df, params):
    std_multiplier = params.get("std_multiplier", 1.5)

    df["vwap"] = (df["volume"] * (df["high"] + df["low"] + df["close"]) / 3).cumsum() / df["volume"].cumsum()
    df["vwap_dev"] = (df["close"] - df["vwap"]) / df["vwap"]

    entries = (df["vwap_dev"] < -std_multiplier * 0.01) & (df["vwap_dev"].shift(1) >= -std_multiplier * 0.01)
    exits = (df["vwap_dev"] > 0) & (df["vwap_dev"].shift(1) <= 0)

    return entries.fillna(False), exits.fillna(False)
''',

    "OBV 動量": '''# OBV (On-Balance Volume) 動量策略
# OBV 突破其均線 → 進場
# OBV 跌破其均線 → 出場

def generate_signals(df, params):
    obv_ma = params.get("obv_ma", 20)

    obv = [0]
    for i in range(1, len(df)):
        if df["close"].iloc[i] > df["close"].iloc[i-1]:
            obv.append(obv[-1] + df["volume"].iloc[i])
        elif df["close"].iloc[i] < df["close"].iloc[i-1]:
            obv.append(obv[-1] - df["volume"].iloc[i])
        else:
            obv.append(obv[-1])
    df["obv"] = obv
    df["obv_sma"] = df["obv"].rolling(obv_ma).mean()

    entries = (df["obv"] > df["obv_sma"]) & (df["obv"].shift(1) <= df["obv_sma"].shift(1))
    exits = (df["obv"] < df["obv_sma"]) & (df["obv"].shift(1) >= df["obv_sma"].shift(1))

    return entries.fillna(False), exits.fillna(False)
''',

    "一目均衡表 (Ichimoku)": '''# 一目均衡表策略
# 價格在雲之上 + 轉換線 > 基準線 + 遲行線 > 價格 → 進場
# 反轉訊號 → 出場

def generate_signals(df, params):
    conv = params.get("conversion", 9)
    base = params.get("base", 26)
    span_b = params.get("span_b", 52)

    df["tenkan"] = (df["high"].rolling(conv).max() + df["low"].rolling(conv).min()) / 2
    df["kijun"] = (df["high"].rolling(base).max() + df["low"].rolling(base).min()) / 2
    df["senkou_a"] = ((df["tenkan"] + df["kijun"]) / 2).shift(base)
    df["senkou_b"] = ((df["high"].rolling(span_b).max() + df["low"].rolling(span_b).min()) / 2).shift(base)
    df["cloud_top"] = df[["senkou_a", "senkou_b"]].max(axis=1)
    df["cloud_bottom"] = df[["senkou_a", "senkou_b"]].min(axis=1)

    # 多頭：價格 > 雲頂 + 轉換 > 基準
    bull = (df["close"] > df["cloud_top"]) & (df["tenkan"] > df["kijun"])
    bear = (df["close"] < df["cloud_bottom"]) & (df["tenkan"] < df["kijun"])

    entries = bull & (~bull.shift(1).fillna(False))
    exits = bear & (~bear.shift(1).fillna(False))

    return entries.fillna(False), exits.fillna(False)
''',

    "Parabolic SAR 趨勢": '''# Parabolic SAR 趨勢跟蹤策略
# 價格從下方穿越 SAR → 進場做多
# 價格從上方穿越 SAR → 出場

def generate_signals(df, params):
    af_start = params.get("af_start", 0.02)
    af_step = params.get("af_step", 0.02)
    af_max = params.get("af_max", 0.2)

    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    n = len(df)

    sar = np.zeros(n)
    trend = np.ones(n)  # 1=up, -1=down
    af = np.zeros(n)
    ep = np.zeros(n)  # Extreme Point

    # 初始化
    sar[0] = low[0]
    ep[0] = high[0]
    af[0] = af_start
    trend[0] = 1

    for i in range(1, n):
        if trend[i-1] == 1:  # 上漲趨勢
            sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
            sar[i] = min(sar[i], low[i-1], low[max(0, i-2)] if i >= 2 else low[i-1])
            if low[i] < sar[i]:  # 反轉
                trend[i] = -1
                sar[i] = ep[i-1]
                ep[i] = low[i]
                af[i] = af_start
            else:
                trend[i] = 1
                ep[i] = max(ep[i-1], high[i])
                af[i] = min(af[i-1] + af_step, af_max) if high[i] > ep[i-1] else af[i-1]
        else:  # 下跌趨勢
            sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
            sar[i] = max(sar[i], high[i-1], high[max(0, i-2)] if i >= 2 else high[i-1])
            if high[i] > sar[i]:  # 反轉
                trend[i] = 1
                sar[i] = ep[i-1]
                ep[i] = high[i]
                af[i] = af_start
            else:
                trend[i] = -1
                ep[i] = min(ep[i-1], low[i])
                af[i] = min(af[i-1] + af_step, af_max) if low[i] < ep[i-1] else af[i-1]

    df["sar"] = sar
    df["trend"] = trend

    entries = (df["trend"] == 1) & (df["trend"].shift(1) == -1)
    exits = (df["trend"] == -1) & (df["trend"].shift(1) == 1)

    return entries.fillna(False), exits.fillna(False)
''',

    "布林通道 雙向 (Bollinger Bands Long+Short)": '''# 布林通道雙向策略
# 價格跌破下軌 → 做多（均值回歸）
# 價格漲破上軌 → 做空（均值回歸）
# 回到中軌 → 平倉
#
# 回傳格式（雙向模式需要 4 個 series）：
#   long_entries, long_exits, short_entries, short_exits

def generate_signals(df, params):
    period = params.get("bb_period", 20)
    num_std = params.get("num_std", 2.0)

    df["bb_mid"] = df["close"].rolling(period).mean()
    df["bb_std"] = df["close"].rolling(period).std()
    df["bb_upper"] = df["bb_mid"] + num_std * df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - num_std * df["bb_std"]

    long_entries = (df["close"] < df["bb_lower"]) & (df["close"].shift(1) >= df["bb_lower"].shift(1))
    long_exits = (df["close"] > df["bb_mid"]) & (df["close"].shift(1) <= df["bb_mid"].shift(1))

    short_entries = (df["close"] > df["bb_upper"]) & (df["close"].shift(1) <= df["bb_upper"].shift(1))
    short_exits = (df["close"] < df["bb_mid"]) & (df["close"].shift(1) >= df["bb_mid"].shift(1))

    return (
        long_entries.fillna(False),
        long_exits.fillna(False),
        short_entries.fillna(False),
        short_exits.fillna(False),
    )
''',

    "BTC/ETH 比率配對 (Bollinger)": '''# BTC/ETH 比率配對交易策略
# 進場：比率跌破下軌 → 做多比率（買 BTC + 空 ETH）
# 進場：比率突破上軌 → 做空比率（空 BTC + 買 ETH）
# 出場：回到均線 / 觸碰對側軌道 / 固定 TP/SL
#
# 注意：這是配對交易策略，需要 PairBacktestEngine
# 在 app.py 中選擇「配對交易模式」才能正確執行

def generate_signals(df, params):
    lookback = params.get("lookback", 100)
    sd_mult = params.get("sd_mult", 3.0)
    tp_percent = params.get("tp_percent", 5.0)
    sl_percent = params.get("sl_percent", 2.5)
    use_ma_exit = params.get("use_ma_exit", True)
    use_tp_sl = params.get("use_tp_sl", True)
    use_opposite_exit = params.get("use_opposite_exit", False)

    # 計算比率
    if "ratio" not in df.columns:
        # 假設 df 是合併後的 pair data，有兩個 close
        # 自動尋找兩個 close 欄位
        close_cols = [c for c in df.columns if c.endswith("_close")]
        if len(close_cols) >= 2:
            df["ratio"] = df[close_cols[0]] / df[close_cols[1]]
        else:
            # 單一標的，把 close 當作比率
            df["ratio"] = df["close"]

    ratio = df["ratio"]
    df["ma"] = ratio.rolling(lookback).mean()
    df["std"] = ratio.rolling(lookback).std()
    df["upper"] = df["ma"] + sd_mult * df["std"]
    df["lower"] = df["ma"] - sd_mult * df["std"]

    entries = pd.Series(False, index=df.index)
    exits = pd.Series(False, index=df.index)

    position = 0
    entry_ratio = 0.0

    start_idx = lookback
    for i in range(start_idx, len(df)):
        if pd.isna(df["ma"].iloc[i]) or pd.isna(df["upper"].iloc[i]) or pd.isna(df["lower"].iloc[i]):
            continue

        curr_ratio = ratio.iloc[i]
        curr_ma = df["ma"].iloc[i]
        curr_upper = df["upper"].iloc[i]
        curr_lower = df["lower"].iloc[i]

        if position == 0:
            # 多比率進場
            if curr_ratio < curr_lower:
                position = 1
                entry_ratio = curr_ratio
                entries.iloc[i] = True
            # 空比率進場
            elif curr_ratio > curr_upper:
                position = -1
                entry_ratio = curr_ratio
                entries.iloc[i] = True
        else:
            is_exit = False
            # 回到均線
            if use_ma_exit:
                if position == 1 and curr_ratio >= curr_ma:
                    is_exit = True
                elif position == -1 and curr_ratio <= curr_ma:
                    is_exit = True

            # 觸碰對側軌道
            if not is_exit and use_opposite_exit:
                if position == 1 and curr_ratio >= curr_upper:
                    is_exit = True
                elif position == -1 and curr_ratio <= curr_lower:
                    is_exit = True

            # 固定 TP/SL
            if not is_exit and use_tp_sl:
                if position == 1:
                    tp = entry_ratio * (1 + tp_percent / 100)
                    sl = entry_ratio * (1 - sl_percent / 100)
                    if curr_ratio >= tp or curr_ratio <= sl:
                        is_exit = True
                elif position == -1:
                    tp = entry_ratio * (1 - tp_percent / 100)
                    sl = entry_ratio * (1 + sl_percent / 100)
                    if curr_ratio <= tp or curr_ratio >= sl:
                        is_exit = True

            if is_exit:
                exits.iloc[i] = True
                position = 0
                entry_ratio = 0.0

    return entries.fillna(False), exits.fillna(False)
''',
}


def get_template(name: str) -> str:
    """取得策略範本"""
    return STRATEGY_TEMPLATES.get(name, "")


def list_templates() -> list:
    """列出所有可用的策略範本"""
    return list(STRATEGY_TEMPLATES.keys())


def get_param_space(name: str) -> Dict[str, list]:
    """
    取得策略的預設參數搜尋空間
    用於自動參數優化
    """
    spaces = {
        "均線交叉 (SMA Crossover)": {
            "fast_period": [5, 10, 15, 20, 25, 30],
            "slow_period": [30, 40, 50, 60, 80, 100],
        },
        "RSI 超買超賣": {
            "rsi_period": [7, 10, 14, 21],
            "entry_level": [20, 25, 30, 35],
            "exit_level": [65, 70, 75, 80],
        },
        "布林通道 (Bollinger Bands)": {
            "bb_period": [15, 20, 25, 30],
            "num_std": [1.5, 2.0, 2.5, 3.0],
        },
        "布林通道 雙向 (Bollinger Bands Long+Short)": {
            "bb_period": [15, 20, 25, 30],
            "num_std": [1.5, 2.0, 2.5, 3.0],
        },
        "MACD 交叉": {
            "fast": [8, 10, 12, 15],
            "slow": [20, 24, 26, 30],
            "signal": [7, 9, 11, 13],
        },
        "網格交易 (Grid Trading)": {
            "grid_size": [0.01, 0.015, 0.02, 0.03, 0.05],
            "lookback": [10, 20, 30, 50],
        },
        "海龜交易 (Turtle)": {
            "entry_break": [10, 15, 20, 30, 50],
            "exit_break": [5, 10, 15, 20],
        },
        "KDJ 隨機指標": {
            "n": [5, 9, 14, 21],
            "m1": [2, 3, 5],
            "m2": [2, 3, 5],
        },
        "CCI 順勢指標": {
            "cci_period": [10, 14, 20, 30],
            "entry_level": [-150, -120, -100, -80],
            "exit_level": [80, 100, 120, 150],
        },
        "Donchian Channels 突破": {
            "entry_n": [10, 15, 20, 30, 50],
            "exit_n": [5, 8, 10, 15],
        },
        "三重 EMA (TEMA)": {
            "ema1": [3, 5, 8, 10],
            "ema2": [15, 20, 25, 30],
            "ema3": [40, 50, 60, 80],
        },
        "VWAP 偏離策略": {
            "std_multiplier": [1.0, 1.5, 2.0, 2.5, 3.0],
        },
        "OBV 動量": {
            "obv_ma": [10, 15, 20, 30, 50],
        },
        "一目均衡表 (Ichimoku)": {
            "conversion": [7, 9, 12],
            "base": [22, 26, 30],
            "span_b": [44, 52, 60],
        },
        "Parabolic SAR 趨勢": {
            "af_start": [0.01, 0.02, 0.03],
            "af_step": [0.01, 0.02, 0.03],
            "af_max": [0.1, 0.2, 0.3],
        },
        "BTC/ETH 比率配對 (Bollinger)": {
            "lookback": [50, 100, 150, 200],
            "sd_mult": [2.0, 2.5, 3.0, 3.5],
            "tp_percent": [3.0, 5.0, 7.0, 10.0],
            "sl_percent": [1.5, 2.5, 3.5, 5.0],
        },
    }
    return spaces.get(name, {})


def get_default_params(name: str) -> Dict[str, Any]:
    """取得策略的預設參數"""
    defaults = {
        "均線交叉 (SMA Crossover)": {"fast_period": 20, "slow_period": 50},
        "RSI 超買超賣": {"rsi_period": 14, "entry_level": 30, "exit_level": 70},
        "布林通道 (Bollinger Bands)": {"bb_period": 20, "num_std": 2.0},
        "布林通道 雙向 (Bollinger Bands Long+Short)": {"bb_period": 20, "num_std": 2.0},
        "MACD 交叉": {"fast": 12, "slow": 26, "signal": 9},
        "網格交易 (Grid Trading)": {"grid_size": 0.02, "lookback": 20},
        "海龜交易 (Turtle)": {"entry_break": 20, "exit_break": 10},
        "KDJ 隨機指標": {"n": 9, "m1": 3, "m2": 3},
        "CCI 順勢指標": {"cci_period": 20, "entry_level": -100, "exit_level": 100},
        "Donchian Channels 突破": {"entry_n": 20, "exit_n": 10},
        "三重 EMA (TEMA)": {"ema1": 5, "ema2": 20, "ema3": 50},
        "VWAP 偏離策略": {"std_multiplier": 1.5},
        "OBV 動量": {"obv_ma": 20},
        "一目均衡表 (Ichimoku)": {"conversion": 9, "base": 26, "span_b": 52},
        "Parabolic SAR 趨勢": {"af_start": 0.02, "af_step": 0.02, "af_max": 0.2},
        "BTC/ETH 比率配對 (Bollinger)": {"lookback": 100, "sd_mult": 3.0, "tp_percent": 5.0, "sl_percent": 2.5, "use_ma_exit": True, "use_tp_sl": True, "use_opposite_exit": False},
    }
    return defaults.get(name, {})
