"""
predict_5m_accuracy.py — 直接預測 5m BTC 漲跌方向，不看 P&L。
用 1m 數據，每 5 根 K 線預測下一根 5m 收盤方向。
評估指標：準確率 (Accuracy) > 55% 才能在 Polymarket 賺錢。
"""
import os, sys, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    # ensure numeric
    for c in ('open','high','low','close','volume'):
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df

def supertrend_dir(high, low, close, period: int, multiplier: float):
    """Return array of supertrend direction (1=bull, -1=bear)"""
    n = len(close)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
    atr = np.convolve(tr, np.ones(period)/period, mode='same')
    atr[:period] = 0

    hl2 = (high + low) / 2
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr

    direction = np.zeros(n, dtype=int)
    st_upper = np.zeros(n)
    st_lower = np.zeros(n)

    for i in range(period + 1, n):
        prev_dir = direction[i-1]
        prev_upper = st_upper[i-1]
        prev_lower = st_lower[i-1]

        if close[i] > upper[i]:
            direction[i] = 1
        elif close[i] < lower[i]:
            direction[i] = -1
        else:
            direction[i] = prev_dir

        if direction[i] == 1:
            st_upper[i] = min(upper[i], prev_upper) if prev_upper > 0 else upper[i]
            st_lower[i] = lower[i]
        else:
            st_lower[i] = max(lower[i], prev_lower) if prev_lower > 0 else lower[i]
            st_upper[i] = upper[i]

    return direction

def evaluate_strategy(df: pd.DataFrame, params: dict) -> dict:
    """Run prediction strategy and return accuracy metrics."""
    h = df['high'].values
    l = df['low'].values
    c = df['close'].values
    v = df['volume'].values
    n = len(c)

    # Params
    atr_p = [params.get('atr_p1',10), params.get('atr_p2',11), params.get('atr_p3',12)]
    mult = [params.get('mult1',1.0), params.get('mult2',2.0), params.get('mult3',3.0)]
    min_votes = params.get('min_votes', 2)
    bb_period = params.get('bb_period', 20)
    bb_std = params.get('bb_std', 2.0)
    lookback = params.get('squeeze_lookback', 120)
    bw_th = params.get('bw_threshold', 0.15)

    # Supertrend
    st_dirs = []
    for p, m in zip(atr_p, mult):
        st_dirs.append(supertrend_dir(h, l, c, p, m))

    # BB bandwidth history
    bb_mid = np.convolve(c, np.ones(bb_period)/bb_period, mode='same')
    bb_std_arr = np.zeros(n)
    for i in range(bb_period, n):
        bb_std_arr[i] = np.std(c[i-bb_period+1:i+1]) * bb_std
    bw = np.zeros(n)
    for i in range(bb_period, n):
        if bb_mid[i] != 0:
            bw[i] = (2 * bb_std_arr[i]) / bb_mid[i]

    # BW history for percentile
    bw_hist = bw.copy()
    bw_hist[bw_hist <= 0] = np.nan

    # Predictions
    predictions = []  # (predicted_direction, actual_direction, confidence)
    warmup = max(max(atr_p), bb_period, lookback) + 10

    for i in range(warmup, n - 5, 5):  # every 5 bars
        # Multi-Supertrend votes
        votes_up = sum(1 for st in st_dirs if st[i] == 1)
        votes_dn = sum(1 for st in st_dirs if st[i] == -1)

        if votes_up < min_votes and votes_dn < min_votes:
            continue  # no clear signal

        pred_dir = 1 if votes_up >= min_votes else -1

        # BB squeeze
        current_bw = bw[i]
        if current_bw <= 0:
            continue

        bw_vals = bw_hist[max(0,i-lookback):i+1]
        bw_vals = bw_vals[~np.isnan(bw_vals)]
        if len(bw_vals) < 20:
            continue

        bw_min = np.percentile(bw_vals, 10)
        bw_max = np.percentile(bw_vals, 90)
        if bw_max - bw_min < 1e-9:
            continue

        bw_norm = (current_bw - bw_min) / (bw_max - bw_min)
        recent5 = bw_vals[-5:] if len(bw_vals) >= 5 else bw_vals
        prev5 = bw_vals[-10:-5] if len(bw_vals) >= 10 else bw_vals[:5]
        expanding = np.mean(recent5) > np.mean(prev5) * 1.02 if len(prev5) > 0 else False

        if bw_norm < bw_th and not expanding:
            continue  # still squeezed, skip

        # Actual direction: close[i+5] vs close[i]
        actual_dir = 1 if c[i+5] > c[i] else (-1 if c[i+5] < c[i] else 0)
        if actual_dir == 0:
            continue

        # Confidence: how many votes
        confidence = max(votes_up, votes_dn) / 3.0
        predictions.append((pred_dir, actual_dir, confidence))

    if not predictions:
        return {"accuracy": 0, "total": 0, "correct": 0, "msg": "no signals"}

    total = len(predictions)
    correct = sum(1 for p, a, _ in predictions if p == a)
    accuracy = correct / total

    # Separate up/down accuracy
    up_preds = [(p, a) for p, a, _ in predictions if p == 1]
    dn_preds = [(p, a) for p, a, _ in predictions if p == -1]
    up_acc = sum(1 for _, a in up_preds if a == 1) / len(up_preds) if up_preds else 0
    dn_acc = sum(1 for _, a in dn_preds if a == -1) / len(dn_preds) if dn_preds else 0

    return {
        "accuracy": round(accuracy, 4),
        "total": total,
        "correct": correct,
        "up_accuracy": round(up_acc, 4),
        "dn_accuracy": round(dn_acc, 4),
        "up_total": len(up_preds),
        "dn_total": len(dn_preds),
        "avg_confidence": round(np.mean([c for _, _, c in predictions]), 4),
    }


def main():
    csv_path = os.path.join(ROOT, "data", "csv", "BTC_USDT_1m.csv")
    df = load_csv(csv_path)
    print(f"Data: {len(df)} bars, {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")

    # Test default params
    default_params = {
        "atr_p1": 10, "atr_p2": 11, "atr_p3": 12,
        "mult1": 1.0, "mult2": 2.0, "mult3": 3.0,
        "min_votes": 2,
        "bb_period": 20, "bb_std": 2.0,
        "squeeze_lookback": 120, "bw_threshold": 0.15,
    }
    r = evaluate_strategy(df, default_params)
    print(f"\n=== Default params ===")
    print(f"  Accuracy:  {r['accuracy']*100:.1f}%")
    print(f"  Signals:   {r['total']} ({r['correct']} correct)")
    print(f"  Up acc:    {r['up_accuracy']*100:.1f}% ({r['up_total']} preds)")
    print(f"  Down acc:  {r['dn_accuracy']*100:.1f}% ({r['dn_total']} preds)")
    print(f"  Confidence:{r['avg_confidence']:.2f}")

    # Try simpler: just use 1-layer Supertrend, no BB filter
    simple_params = {
        "atr_p1": 10, "atr_p2": 10, "atr_p3": 10,
        "mult1": 2.0, "mult2": 2.0, "mult3": 2.0,
        "min_votes": 1,
        "bb_period": 20, "bb_std": 2.0,
        "squeeze_lookback": 120, "bw_threshold": 1.0,  # no squeeze filter
    }
    r2 = evaluate_strategy(df, simple_params)
    print(f"\n=== Simple (1 Supertrend, no BB filter) ===")
    print(f"  Accuracy:  {r2['accuracy']*100:.1f}%")
    print(f"  Signals:   {r2['total']} ({r2['correct']} correct)")
    print(f"  Up acc:    {r2['up_accuracy']*100:.1f}% ({r2['up_total']} preds)")
    print(f"  Down acc:  {r2['dn_accuracy']*100:.1f}% ({r2['dn_total']} preds)")
    print(f"  Confidence:{r2['avg_confidence']:.2f}")

    # Try: price momentum (last 3 bars direction)
    print(f"\n=== Price momentum (last 3 bars) ===")
    c = df['close'].values
    momentum_preds = []
    warmup = 10
    for i in range(warmup, len(c) - 5, 5):
        mom = 1 if c[i] > c[i-3] else (-1 if c[i] < c[i-3] else 0)
        if mom == 0:
            continue
        actual = 1 if c[i+5] > c[i] else (-1 if c[i+5] < c[i] else 0)
        if actual == 0:
            continue
        momentum_preds.append((mom, actual))

    if momentum_preds:
        mom_acc = sum(1 for p, a in momentum_preds if p == a) / len(momentum_preds)
        print(f"  Accuracy:  {mom_acc*100:.1f}%")
        print(f"  Signals:   {len(momentum_preds)}")
        up_m = [(p,a) for p,a in momentum_preds if p==1]
        dn_m = [(p,a) for p,a in momentum_preds if p==-1]
        print(f"  Up acc:    {sum(1 for _,a in up_m if a==1)/len(up_m)*100:.1f}% ({len(up_m)} preds)" if up_m else "  Up: 0")
        print(f"  Down acc:  {sum(1 for _,a in dn_m if a==1)/len(dn_m)*100:.1f}% ({len(dn_m)} preds)" if dn_m else "  Down: 0")

    # Try: RSI-based
    print(f"\n=== RSI(14) oversold/overbought ===")
    from ta.momentum import RSIIndicator
    rsi = RSIIndicator(close=df['close'], window=14).rsi().values
    rsi_preds = []
    for i in range(20, len(c) - 5, 5):
        if rsi[i] < 30:  # oversold -> predict up
            pred = 1
        elif rsi[i] > 70:  # overbought -> predict down
            pred = -1
        else:
            continue
        actual = 1 if c[i+5] > c[i] else (-1 if c[i+5] < c[i] else 0)
        if actual == 0:
            continue
        rsi_preds.append((pred, actual))

    if rsi_preds:
        rsi_acc = sum(1 for p, a in rsi_preds if p == a) / len(rsi_preds)
        print(f"  Accuracy:  {rsi_acc*100:.1f}%")
        print(f"  Signals:   {len(rsi_preds)}")

if __name__ == "__main__":
    main()