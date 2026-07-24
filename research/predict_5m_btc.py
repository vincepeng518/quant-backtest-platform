"""
predict_5m_btc.py — 嘗試多種特徵預測 BTC 5m 漲跌方向。
用 1m 數據，每 5 根 K 線預測下一根 5m 收盤方向。
"""
import os, sys, numpy as np, pandas as pd
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    for c in ('open','high','low','close','volume'):
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df

def main():
    csv_path = os.path.join(ROOT, "data", "csv", "BTC_USDT_1m.csv")
    df = load_csv(csv_path)
    c = df['close'].values
    h = df['high'].values
    l = df['low'].values
    v = df['volume'].values
    n = len(c)
    print(f"Data: {n} bars, {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
    print()

    # Convert 1m to 5m candles
    # Each 5m candle = 5 x 1m
    c5 = c[4::5]  # close of every 5th bar
    h5 = np.array([max(h[i:i+5]) for i in range(0, n-4, 5)])
    l5 = np.array([min(l[i:i+5]) for i in range(0, n-4, 5)])
    v5 = np.array([sum(v[i:i+5]) for i in range(0, n-4, 5)])
    n5 = len(c5)
    print(f"5m candles: {n5}")

    # Test 1: Last 5m direction predicts next 5m direction
    print("\n=== 1. 上一根 5m 方向 → 下一根 5m 方向 ===")
    preds = []
    for i in range(1, n5 - 1):
        prev_dir = 1 if c5[i] > c5[i-1] else (-1 if c5[i] < c5[i-1] else 0)
        if prev_dir == 0: continue
        actual = 1 if c5[i+1] > c5[i] else (-1 if c5[i+1] < c5[i] else 0)
        if actual == 0: continue
        preds.append((prev_dir, actual))
    if preds:
        acc = sum(1 for p, a in preds if p == a) / len(preds)
        print(f"  Accuracy: {acc*100:.1f}% ({len(preds)} signals)")

    # Test 2: Last 5m range (high-low) predicts next 5m direction
    print("\n=== 2. 5m 實體大小 vs 影線比例 ===")
    preds = []
    for i in range(1, n5 - 1):
        body = abs(c5[i] - c5[i-1])
        wick = h5[i] - l5[i] - body
        if wick > body * 1.5:  # 長影線 = 反轉訊號
            pred = 1 if c5[i] < c5[i-1] else -1  # 長下影線→漲, 長上影線→跌
        else:
            continue
        actual = 1 if c5[i+1] > c5[i] else (-1 if c5[i+1] < c5[i] else 0)
        if actual == 0: continue
        preds.append((pred, actual))
    if preds:
        acc = sum(1 for p, a in preds if p == a) / len(preds)
        print(f"  Accuracy: {acc*100:.1f}% ({len(preds)} signals)")

    # Test 3: 1m volume surge before 5m close
    print("\n=== 3. 最後1分鐘量暴增 ===")
    preds = []
    for i in range(5, n - 5, 5):
        last_v = v[i-1]
        avg_v = np.mean(v[i-5:i-1])
        if avg_v > 0 and last_v > avg_v * 2:  # 量暴增2倍
            pred = 1 if c[i-1] > c[i-2] else -1
        else:
            continue
        actual = 1 if c[i+4] > c[i-1] else (-1 if c[i+4] < c[i-1] else 0)
        if actual == 0: continue
        preds.append((pred, actual))
    if preds:
        acc = sum(1 for p, a in preds if p == a) / len(preds)
        print(f"  Accuracy: {acc*100:.1f}% ({len(preds)} signals)")

    # Test 4: ATR regime (high vol = trend continuation, low vol = reversal)
    print("\n=== 4. 波動率體制 (ATR) ===")
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    atr20 = np.convolve(tr, np.ones(20)/20, mode='same')
    atr20[:20] = atr20[20]
    
    preds = []
    for i in range(20, n - 5, 5):
        atr_z = (tr[i] - atr20[i]) / (atr20[i] + 1e-9)
        if atr_z > 0.5:  # 高波動
            # 順勢：前一根方向 = 下一根方向
            trend = 1 if c[i] > c[i-5] else -1
            pred = trend
        elif atr_z < -0.5:  # 低波動
            # 均值回歸：反向
            pred = 1 if c[i] < c[i-5] else -1
        else:
            continue
        actual = 1 if c[i+4] > c[i] else (-1 if c[i+4] < c[i] else 0)
        if actual == 0: continue
        preds.append((pred, actual))
    if preds:
        acc = sum(1 for p, a in preds if p == a) / len(preds)
        print(f"  Accuracy: {acc*100:.1f}% ({len(preds)} signals)")

    # Test 5: 1m candle pattern (engulfing, pin bar) 
    print("\n=== 5. K 線型態 (前1m吞噬) ===")
    preds = []
    for i in range(2, n - 5, 5):
        prev_body = abs(c[i-1] - c[i-2])
        prev_range = h[i-1] - l[i-1]
        curr_body = abs(c[i] - c[i-1])
        curr_range = h[i] - l[i]
        
        # Bullish engulfing: current green covers previous red
        if (c[i] > c[i-1] and c[i-1] < c[i-2] and 
            c[i] > h[i-2] and c[i-1] < l[i-2]):
            pred = 1
        # Bearish engulfing
        elif (c[i] < c[i-1] and c[i-1] > c[i-2] and 
              c[i] < l[i-2] and c[i-1] > h[i-2]):
            pred = -1
        else:
            continue
        actual = 1 if c[i+4] > c[i] else (-1 if c[i+4] < c[i] else 0)
        if actual == 0: continue
        preds.append((pred, actual))
    if preds:
        acc = sum(1 for p, a in preds if p == a) / len(preds)
        print(f"  Accuracy: {acc*100:.1f}% ({len(preds)} signals, expected ~55%+ for viability)")

    # Test 6: Combined — momentum + volume + volatility
    print("\n=== 6. 綜合評分 (動量+量+波動率) ===")
    preds = []
    for i in range(20, n - 5, 5):
        score = 0
        # Momentum: last 3 bars
        mom = (c[i] - c[i-3]) / c[i]
        score += 1 if mom > 0.0003 else (-1 if mom < -0.0003 else 0)
        # Volume relative to avg
        vol_ratio = v[i] / (np.mean(v[i-5:i]) + 1e-9)
        score += 1 if vol_ratio > 1.5 else 0
        # Range expansion
        rng = h[i] - l[i]
        avg_rng = np.mean([h[j]-l[j] for j in range(i-5, i)])
        score += 1 if rng > avg_rng * 1.2 else 0
        
        if abs(score) < 2:
            continue  # need at least 2 signals
        
        pred = 1 if score > 0 else -1
        actual = 1 if c[i+4] > c[i] else (-1 if c[i+4] < c[i] else 0)
        if actual == 0: continue
        preds.append((pred, actual))
    if preds:
        acc = sum(1 for p, a in preds if p == a) / len(preds)
        up = sum(1 for p, a in preds if p == 1 and a == 1)
        dn = sum(1 for p, a in preds if p == -1 and a == -1)
        print(f"  Accuracy: {acc*100:.1f}% ({len(preds)} signals)")
        print(f"  Up: {up} correct, Down: {dn} correct")

    # Test 7: Polymarket lastTradePrice as signal
    print("\n=== 7. Polymarket lastTradePrice 模擬 ===")
    print("  (無法取得歷史資料，需實盤測試)")
    print("   邏輯: lastTradePrice > 0.55 → 看漲, < 0.45 → 看跌")
    print("   當前: 0.51 (中性)")

    # Test 8: Simple 5m momentum (no 1m conversion)
    print("\n=== 8. 5m RSI 動量 ===")
    preds = []
    for i in range(15, n5 - 1):
        # RSI on 5m data
        gains = [max(0, c5[j] - c5[j-1]) for j in range(i-13, i+1)]
        losses = [max(0, c5[j-1] - c5[j]) for j in range(i-13, i+1)]
        avg_g = np.mean(gains) if gains else 0
        avg_l = np.mean(losses) if losses else 0
        rs = avg_g / (avg_l + 1e-9)
        rsi = 100 - 100 / (1 + rs)
        
        if rsi < 30:
            pred = 1  # oversold
        elif rsi > 70:
            pred = -1  # overbought
        else:
            continue
        
        actual = 1 if c5[i+1] > c5[i] else (-1 if c5[i+1] < c5[i] else 0)
        if actual == 0: continue
        preds.append((pred, actual))
    if preds:
        acc = sum(1 for p, a in preds if p == a) / len(preds)
        print(f"  Accuracy: {acc*100:.1f}% ({len(preds)} signals)")

if __name__ == "__main__":
    main()