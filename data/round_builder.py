from __future__ import annotations

import pandas as pd


def build_rounds(df_1m: pd.DataFrame, round_minutes: int = 5) -> pd.DataFrame:
    """把 1m K 線聚合成 N 分鐘「輪次」Bar，並注入 metadata：
      - round_id: 輪次序號
      - round_open: 輪次開盤價（第一根 1m 的 open）
      - seconds_to_close: 當前 1m 棒距輪次收盤剩餘秒數（含本根中點近似）
      - round_index: 輪內第幾根 1m (1-based)
      - drop_from_open_pct: 從 round_open 到本根 close 的累計跌幅(%)
    回傳 DataFrame 含 timestamp/open/high/low/close/volume/metadata 欄，可直接餵 Backtester。
    """
    df = df_1m.reset_index(drop=True)
    df["round_id"] = (df.index // round_minutes)
    rows = []
    for rid, g in df.groupby("round_id"):
        g = g.reset_index(drop=True)
        round_open = float(g.iloc[0]["open"])
        for k, r in g.iterrows():
            # k: 0-based 輪內位置; 剩餘秒數 = (round_minutes - k) * 60 (中點近似)
            seconds_to_close = (round_minutes - k) * 60
            drop_pct = (round_open - float(r["close"])) / round_open * 100.0
            meta = {
                "round_id": int(rid),
                "round_open": round_open,
                "seconds_to_close": int(seconds_to_close),
                "round_index": int(k + 1),
                "drop_from_open_pct": round(drop_pct, 4),
            }
            rows.append({
                "timestamp": r["timestamp"],
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r["volume"]),
                "metadata": meta,
            })
    return pd.DataFrame(rows)


def add_round_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """在輪次序列上算 RSI(14)（用輪次 close），寫回每根 1m 棒 metadata['rsi']。
    注意：RSI 需要跨輪次連續 close，所以用全局 1m close 算更準；這裡用輪次聚合後的 close 近似。
    """
    closes = df["close"].astype(float)
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    df = df.copy()
    df["_rsi"] = rsi
    df["metadata"] = df.apply(
        lambda row: {**(row["metadata"] or {}), "rsi": (None if pd.isna(row["_rsi"]) else round(float(row["_rsi"]), 2))},
        axis=1,
    )
    df = df.drop(columns=["_rsi"])
    return df
