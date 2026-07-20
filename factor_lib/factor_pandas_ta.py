"""
factor_pandas_ta.py — 用 pandas_ta 對所有 data/csv/*.csv 計算技術指標特徵矩陣。
單標的時間序列 (BTC_USDT_1h 等) 直接適配 pandas_ta (原生單標的 OHLCV 設計)。

用法:
  source /root/ytvenv/bin/activate
  python3 factor_lib/factor_pandas_ta.py [--symbol BTC_USDT] [--tf 1h]

輸出: factor_lib/pandas_ta_features/<SYM>_<TF>.parquet (含 timestamp + 所有成功指標)
依賴: pandas_ta (beta 0.4.71, numpy 2.2.6)
"""
from __future__ import annotations
import os, sys, argparse, traceback
import pandas as pd
import pandas_ta as ta
import inspect

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CSV_DIR = os.path.join(ROOT, "data", "csv")
OUT_DIR = os.path.join(ROOT, "factor_lib", "pandas_ta_features")
os.makedirs(OUT_DIR, exist_ok=True)

# 模組層指標函數 (排除非指標 helper)
SKIP = {
    "settings", "to_", "version", "verbose", "about", "tools", "_",
    "camelCase2Title", "category_files", "combination", "above", "below",
    "above_value", "below_value", "candle_color", "cross", "signals",
}


def list_indicators() -> list[str]:
    out = []
    for name in dir(ta):
        obj = getattr(ta, name)
        if inspect.isfunction(obj) and name[0].islower() and name not in SKIP:
            out.append(name)
    return sorted(out)


def compute(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: c.lower() for c in df.columns})
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            if col.capitalize() in df.columns:
                df[col] = df[col.capitalize()]
    indicators = list_indicators()
    ok, fail = [], []
    for name in indicators:
        try:
            fn = getattr(ta, name)
            # 嘗試呼叫: 多數指標只需 close/ohlcv, 用 kwargs 容錯
            try:
                res = fn(open_=df["open"], high=df["high"], low=df["low"],
                         close=df["close"], volume=df["volume"], append=False)
            except TypeError:
                try:
                    res = fn(high=df["high"], low=df["low"], close=df["close"],
                             volume=df["volume"], append=False)
                except TypeError:
                    res = fn(close=df["close"], append=False)
            if res is None:
                fail.append(name)
                continue
            # 標準化為 DataFrame/columns 加入
            if isinstance(res, pd.DataFrame):
                for c in res.columns:
                    df[f"{name}_{c}" if c in df.columns else c] = res[c]
            elif isinstance(res, pd.Series):
                df[name] = res
            else:
                # 標量或 array
                try:
                    df[name] = res
                except Exception:
                    fail.append(name)
                    continue
            ok.append(name)
        except Exception as e:
            fail.append(f"{name}:{type(e).__name__}")
            continue
    return df, ok, fail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--tf", default=None)
    args = ap.parse_args()

    files = []
    for f in os.listdir(CSV_DIR):
        if not f.endswith(".csv"):
            continue
        tag, tf = f[:-4].rsplit("_", 1) if f[:-4].count("_") else (f[:-4], "")
        if args.symbol and tag != args.symbol:
            continue
        if args.tf and tf != args.tf:
            continue
        files.append(f)
    if not files:
        print("NO CSV MATCH")
        return
    print(f"indicators available: {len(list_indicators())}")
    tot_ok = tot_fail = 0
    for f in files:
        df = pd.read_csv(os.path.join(CSV_DIR, f))
        out, ok, fail = compute(df)
        out_path = os.path.join(OUT_DIR, f.replace(".csv", ".parquet"))
        out.to_parquet(out_path, index=False)
        tot_ok += len(ok)
        tot_fail += len(fail)
        print(f"  {f}: rows={len(out)} factors={len(ok)} fail={len(fail)} -> {os.path.basename(out_path)}")
        if fail:
            print(f"    skipped: {fail[:8]}")
    print(f"DONE total_ok={tot_ok} total_fail={tot_fail}")


if __name__ == "__main__":
    main()
