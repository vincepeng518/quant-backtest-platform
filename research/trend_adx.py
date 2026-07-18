#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADX + DI + MACD 在 BTC/USDT 日線的 3 態趨勢判斷能力驗證
=========================================================

目標：
  用真實 BTC/USDT 日線數據，驗證「ADX + Directional Indicator (DI) + MACD」
  作為日線級別趨勢判斷指標，輸出 3 態信號（看多 / 看空 / 平盤）。

信號規則（提案）：
  - ADX < adx_flat  -> 平盤（趨勢弱，不判方向）
  - ADX >= adx_trend 且 (+DI - -DI) > di_diff  -> 看多
  - ADX >= adx_trend 且 (-DI - +DI) > di_diff  -> 看空
  - 中間地帶（adx_flat <= ADX < adx_trend，或 DI 差值不足）-> 平盤
  - MACD 柱狀圖 slope 作為方向確認：若信號方向與 MACD 柱狀 slope 相反，則降級為平盤
    （避免 ADX 給方向但 MACD 動能已反轉的假突破）

回測定義：
  - 對每日 t 標記信號，對照 t+1 .. t+N 的實際收盤價漲跌。
  - 看多正確：信號=看多 且 N 日後收盤 > 當日收盤
  - 看空正確：信號=看空 且 N 日後收盤 < 當日收盤
  - 平盤正確：信號=平盤 且 N 日後 |收盤漲跌幅| <= flat_band（小於等於盤整帶）
  - 方向準確率 = (看多正確 + 看空正確) / (看多 + 看空 總數)
  - 盤整識別率 = 平盤正確 / 平盤總數

格點搜索：在 (adx_flat, adx_trend, di_diff) 三維格點上尋找使
  score = 0.6*方向準確率 + 0.4*盤整識別率  最大的組合（可作為「最佳閾值」）。

相依：ccxt（主源），yfinance（備援，BTC-USD）。
重跑：python research/trend_adx.py
"""

import sys
import os
import numpy as np
import pandas as pd
from datetime import datetime, timezone

# ---------- 取數 ----------
def load_data():
    """優先用 binance，失敗用 yfinance。回傳 (df, source)。"""
    since = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    try:
        import ccxt
        ex = ccxt.binance()
        print("[data] 嘗試 binance fetch_ohlcv BTC/USDT 1d ...")
        rows = ex.fetch_ohlcv('BTC/USDT', '1d', since=since)
        df = pd.DataFrame(rows, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df['date'] = pd.to_datetime(df['ts'], unit='ms', utc=True).dt.tz_convert(None)
        df = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
        df = df[df['date'] >= '2023-01-01'].reset_index(drop=True)
        print(f"[data] binance OK，{len(df)} 根日線，{df['date'].min().date()} ~ {df['date'].max().date()}")
        return df, 'binance'
    except Exception as e:
        print(f"[data] binance 失敗: {repr(e)[:200]}，改用 yfinance BTC-USD")
        import yfinance as yf
        t = yf.Ticker('BTC-USD')
        df = t.history(start='2023-01-01', interval='1d').reset_index()
        df = df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low',
                                'Close': 'close', 'Volume': 'volume', 'Date': 'date'})
        df = df[['date', 'open', 'high', 'low', 'close', 'volume']].reset_index(drop=True)
        print(f"[data] yfinance OK，{len(df)} 根日線，{df['date'].min().date()} ~ {df['date'].max().date()}")
        return df, 'yfinance'


# ---------- 指標 ----------
def compute_indicators(df, adx_period=14, macd_fast=12, macd_slow=26, macd_sig=9):
    """計算 ADX, +DI, -DI, MACD, MACD signal, histogram, histogram slope。"""
    high, low, close = df['high'], df['low'], df['close']

    # True Range / +DM / -DM
    prev_high, prev_low, prev_close = high.shift(1), low.shift(1), close.shift(1)
    tr = np.maximum.reduce([
        (high - low).abs(),
        (high - prev_high).abs(),
        (low - prev_low).abs(),
    ])
    plus_dm = np.where((high - prev_high) > (prev_low - low),
                       np.maximum(high - prev_high, 0.0), 0.0)
    minus_dm = np.where((prev_low - low) > (high - prev_high),
                        np.maximum(prev_low - low, 0.0), 0.0)

    # Wilder 平滑（含正確的起始點）
    # start: 基礎序列第一個有效值之後 period 個，才做首值平均。
    def wilder_smooth(series, period, start):
        s = np.asarray(series, dtype=float)
        out = np.full(len(s), np.nan)
        # 第一個平滑值 = 從 start-period+1 到 start 共 period 個平均
        first_vals = s[start - period + 1:start + 1]
        first = np.nanmean(first_vals)
        out[start] = first
        for i in range(start + 1, len(s)):
            out[i] = out[i - 1] - out[i - 1] / period + s[i] / period
        return out

    atr = wilder_smooth(tr, adx_period, adx_period)                     # TR[0]=nan, 首值於 index 14
    plus_di_raw = wilder_smooth(plus_dm, adx_period, adx_period)
    minus_di_raw = wilder_smooth(minus_dm, adx_period, adx_period)

    plus_di = 100 * plus_di_raw / atr
    minus_di = 100 * minus_di_raw / atr
    dx = 100 * np.abs(plus_di - minus_di) / np.where((plus_di + minus_di) == 0, np.nan, (plus_di + minus_di))
    # DX 首值在 index 2*period-1（DI 平滑後才有效），ADX 再對 DX 做 Wilder 平滑
    adx = wilder_smooth(dx, adx_period, 2 * adx_period - 1)

    # MACD
    ema_fast = close.ewm(span=macd_fast, adjust=False).mean()
    ema_slow = close.ewm(span=macd_slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=macd_sig, adjust=False).mean()
    macd_hist = macd - macd_signal
    macd_hist_slope = macd_hist.diff(1)  # >0 動能向上, <0 動能向下

    out = df.copy()
    out['adx'] = adx
    out['plus_di'] = plus_di
    out['minus_di'] = minus_di
    out['di_diff'] = plus_di - minus_di
    out['macd'] = macd
    out['macd_hist'] = macd_hist
    out['macd_hist_slope'] = macd_hist_slope
    return out


# ---------- 信號 ----------
def make_signal(df, adx_flat, adx_trend, di_diff, use_macd_confirm=True):
    """
    回傳信號序列: 1=看多, -1=看空, 0=平盤
    MACD 確認：方向信號需與 MACD 柱狀 slope 同向，否則降為平盤。
    """
    adx = df['adx']
    dd = df['di_diff']
    slope = df['macd_hist_slope']

    sig = pd.Series(0, index=df.index, dtype=int)
    trending = adx >= adx_trend
    bull = trending & (dd > di_diff)
    bear = trending & (dd < -di_diff)
    sig[bull] = 1
    sig[bear] = -1

    if use_macd_confirm:
        # 看多但 MACD 柱狀 slope 向下 -> 降級
        mask_bull_bad = (sig == 1) & (slope < 0)
        # 看空但 MACD 柱狀 slope 向上 -> 降級
        mask_bear_bad = (sig == -1) & (slope > 0)
        sig[mask_bull_bad | mask_bear_bad] = 0
    return sig


# ---------- 回測評分 ----------
def evaluate(df, sig, n=5, flat_band=0.02):
    """
    n: 持有 N 日。flat_band: |漲跌幅|<=此值視為盤整。
    回傳 dict 含各項準確率與案例索引。
    """
    close = df['close'].values
    dates = df['date'].values
    future_ret = np.full(len(close), np.nan)
    for i in range(len(close) - n):
        future_ret[i] = close[i + n] / close[i] - 1.0
    future_ret = pd.Series(future_ret, index=df.index)

    bull = sig == 1
    bear = sig == -1
    flat = sig == 0

    bull_ok = bull & (future_ret > 0)
    bear_ok = bear & (future_ret < 0)
    flat_ok = flat & (future_ret.abs() <= flat_band)

    n_bull = int(bull.sum()); n_bear = int(bear.sum()); n_flat = int(flat.sum())
    n_bull_ok = int(bull_ok.sum()); n_bear_ok = int(bear_ok.sum()); n_flat_ok = int(flat_ok.sum())

    dir_total = n_bull + n_bear
    dir_ok = n_bull_ok + n_bear_ok
    dir_acc = dir_ok / dir_total if dir_total else np.nan
    flat_acc = n_flat_ok / n_flat if n_flat else np.nan
    # 整體：方向準確 + 盤整準確 佔總樣本比
    overall = (dir_ok + n_flat_ok) / len(sig)

    # 基準（baseline）：用「前一天漲跌方向」當作預測（動量基準）
    prev_up = pd.Series(np.zeros(len(close)), index=df.index)
    prev_up[1:] = np.sign(np.diff(close))
    base_bull = prev_up == 1
    base_bear = prev_up == -1
    base_dir_ok = int(((base_bull & (future_ret > 0)) | (base_bear & (future_ret < 0))).sum())
    base_dir_total = int((base_bull | base_bear).sum())
    base_dir_acc = base_dir_ok / base_dir_total if base_dir_total else np.nan
    # 純隨機基準：方向日裡 50/50
    rand_dir_acc = 0.5

    # 方向性優勢（edge）= 指標方向準確率 - 隨機基準
    dir_edge = (dir_acc - rand_dir_acc) if dir_acc == dir_acc else np.nan

    return {
        'n': n, 'flat_band': flat_band,
        'n_total': len(sig),
        'n_bull': n_bull, 'n_bear': n_bear, 'n_flat': n_flat,
        'n_bull_ok': n_bull_ok, 'n_bear_ok': n_bear_ok, 'n_flat_ok': n_flat_ok,
        'dir_acc': dir_acc, 'flat_acc': flat_acc, 'overall_acc': overall,
        'base_dir_acc': base_dir_acc, 'dir_edge': dir_edge,
        'bull_idx': df.index[bull_ok].tolist(),
        'bear_idx': df.index[bear_ok].tolist(),
        'flat_idx': df.index[flat_ok].tolist(),
    }, future_ret


# ---------- 格點搜索 ----------
def grid_search(df, n=5):
    adx_flat_grid = [15, 18, 20, 22, 25]
    adx_trend_grid = [22, 25, 28, 30]
    di_diff_grid = [0.0, 1.0, 2.0, 4.0, 6.0]
    best = None
    results = []
    for af in adx_flat_grid:
        for at in adx_trend_grid:
            if at <= af:
                continue
            for dd in di_diff_grid:
                sig = make_signal(df, af, at, dd, use_macd_confirm=True)
                ev, _ = evaluate(df, sig, n=n)
                score = 0.6 * (ev['dir_acc'] if ev['dir_acc'] == ev['dir_acc'] else 0) + 0.4 * (ev['flat_acc'] if ev['flat_acc'] == ev['flat_acc'] else 0)
                results.append((af, at, dd, ev['dir_acc'], ev['flat_acc'], ev['overall_acc'], score))
                if best is None or score > best[1]:
                    best = ((af, at, dd), score, ev)
    res_df = pd.DataFrame(results, columns=['adx_flat', 'adx_trend', 'di_diff', 'dir_acc', 'flat_acc', 'overall_acc', 'score'])
    return best, res_df


def print_examples(df, sig, future_ret, kind, n_needed=2, n_skip=3):
    """印出錯判/典型案例。kind in {'bull_wrong','bear_wrong','flat_wrong'}。"""
    close = df['close'].values
    dates = df['date']
    out = []
    cnt = 0
    for i in range(len(sig) - 5):
        if cnt >= n_needed:
            break
        if kind == 'bull_wrong' and sig[i] == 1 and future_ret[i] <= 0:
            out.append((i, dates[i], close[i], future_ret[i]))
            cnt += 1
        elif kind == 'bear_wrong' and sig[i] == -1 and future_ret[i] >= 0:
            out.append((i, dates[i], close[i], future_ret[i]))
            cnt += 1
        elif kind == 'flat_wrong' and sig[i] == 0 and abs(future_ret[i]) > 0.02:
            out.append((i, dates[i], close[i], future_ret[i]))
            cnt += 1
    return out


def main():
    os.makedirs('research', exist_ok=True)
    df, source = load_data()
    df = compute_indicators(df)
    df = df.dropna(subset=['adx', 'macd_hist_slope']).reset_index(drop=True)
    print(f"[ind] 有效樣本 {len(df)} 根（去掉指標 warmup）")

    n = 5
    flat_band = 0.03  # BTC 5日波動大，盤整帶放寬到 ±3%

    # --- 基礎規則（提案值） ---
    adx_flat0, adx_trend0, di_diff0 = 20, 25, 2.0
    sig0 = make_signal(df, adx_flat0, adx_trend0, di_diff0, use_macd_confirm=True)
    ev0, fr0 = evaluate(df, sig0, n=n, flat_band=flat_band)
    print("\n=== 提案閾值 (adx_flat=20, adx_trend=25, di_diff=2.0, MACD確認=開) ===")
    print(f"  樣本={ev0['n_total']} 看多={ev0['n_bull']} 看空={ev0['n_bear']} 平盤={ev0['n_flat']}")
    print(f"  方向準確率 = {ev0['dir_acc']:.3f}  (基準隨機0.500, 動量基準{ev0['base_dir_acc']:.3f}, edge={ev0['dir_edge']:+.3f})")
    print(f"  盤整識別率 = {ev0['flat_acc']:.3f}  ({ev0['n_flat_ok']}/{ev0['n_flat']})")
    print(f"  整體準確率 = {ev0['overall_acc']:.3f}")

    # --- 格點搜索最佳閾值 ---
    print("\n=== 格點搜索最佳閾值 (score=0.6*方向+0.4*盤整) ===")
    best, res_df = grid_search(df, n=n)
    (af, at, dd), score, evb = best
    print(f"  最佳: adx_flat={af}, adx_trend={at}, di_diff={dd}, score={score:.3f}")
    print(f"    方向準確率={evb['dir_acc']:.3f} (edge={evb['dir_edge']:+.3f})  盤整識別率={evb['flat_acc']:.3f}  整體={evb['overall_acc']:.3f}")
    print("\n  格點結果（按 score 降序 Top10）:")
    print(res_df.sort_values('score', ascending=False).head(10).to_string(index=False))

    # 用最佳閾值重算信號做案例展示
    sig_best = make_signal(df, af, at, dd, use_macd_confirm=True)
    ev_best, fr_best = evaluate(df, sig_best, n=n, flat_band=flat_band)

    # --- 條件診斷：只在 ADX 真正強（>=25）時的方向準確率（剔除平盤干擾） ---
    strong = df['adx'] >= 25
    sig_strong = sig_best[strong]
    fr_strong = fr_best[strong]
    if len(sig_strong):
        ok = ((sig_strong == 1) & (fr_strong > 0)) | ((sig_strong == -1) & (fr_strong < 0))
        strong_acc = ok.sum() / len(sig_strong)
    else:
        strong_acc = np.nan
    print(f"\n=== 條件診斷：ADX>=25 強趨勢日的方向準確率 = {strong_acc:.3f} (樣本{int(strong.sum())}日) ===")

    # --- 錯判案例（用最佳閾值信號） ---
    print("\n=== 錯判案例（最佳閾值信號, N=5 日後反向） ===")
    bull_wrong = print_examples(df, sig_best, fr_best, 'bull_wrong', n_needed=2)
    bear_wrong = print_examples(df, sig_best, fr_best, 'bear_wrong', n_needed=2)
    flat_wrong = print_examples(df, sig_best, fr_best, 'flat_wrong', n_needed=2)
    print("  看多卻下跌（假突破）:")
    for i, d, c, r in bull_wrong:
        print(f"    {d.date()} 收盤={c:,.0f}  5日報酬={r*100:+.2f}%  ADX={df['adx'].iloc[i]:.1f} DI差={df['di_diff'].iloc[i]:.1f}")
    print("  看空卻上漲（假破底）:")
    for i, d, c, r in bear_wrong:
        print(f"    {d.date()} 收盤={c:,.0f}  5日報酬={r*100:+.2f}%  ADX={df['adx'].iloc[i]:.1f} DI差={df['di_diff'].iloc[i]:.1f}")
    print("  判平盤卻劇烈波動（漏判趨勢）:")
    for i, d, c, r in flat_wrong:
        print(f"    {d.date()} 收盤={c:,.0f}  5日報酬={r*100:+.2f}%  ADX={df['adx'].iloc[i]:.1f} DI差={df['di_diff'].iloc[i]:.1f}")

    # --- 無 MACD 確認的對照（說明 MACD 確認的貢獻） ---
    sig_no_confirm = make_signal(df, af, at, dd, use_macd_confirm=False)
    ev_nc, _ = evaluate(df, sig_no_confirm, n=n, flat_band=flat_band)
    print("\n=== 對照：關閉 MACD 確認（同最佳閾值） ===")
    print(f"  方向準確率={ev_nc['dir_acc']:.3f} (edge={ev_nc['dir_edge']:+.3f})  盤整識別率={ev_nc['flat_acc']:.3f}  整體={ev_nc['overall_acc']:.3f}")

    # --- 總結輸出 ---
    print("\n" + "=" * 60)
    print("TLDR / 結論")
    print("=" * 60)
    print(f"數據源: {source}  BTC/USDT 日線  有效樣本 {len(df)} 根 ({df['date'].min().date()}~{df['date'].max().date()})")
    print(f"持有期 N = {n} 日, 盤整帶 = ±{flat_band*100:.0f}%")
    print(f"提案閾值(20/25/2.0): 方向準確率={ev0['dir_acc']:.3f} (edge={ev0['dir_edge']:+.3f}), 盤整識別率={ev0['flat_acc']:.3f}, 整體={ev0['overall_acc']:.3f}")
    print(f"最佳閾值({af}/{at}/{dd}): 方向準確率={evb['dir_acc']:.3f} (edge={evb['dir_edge']:+.3f}), 盤整識別率={evb['flat_acc']:.3f}, 整體={evb['overall_acc']:.3f}")
    print(f"ADX>=25 強趨勢日方向準確率={strong_acc:.3f}")
    print(f"MACD 確認貢獻: 方向準確率 {evb['dir_acc']:.3f} -> (關閉){ev_nc['dir_acc']:.3f}")
    print("建議採用最佳閾值組合作為日線 3 態趨勢判斷基準；注意本指標對 N=5 日漲跌的")
    print("預測力有限（edge 接近 0），更適合做『狀態過濾』而非直接當作進出場信號。")


if __name__ == '__main__':
    main()
