#!/usr/bin/env python3
"""讀 backtest_history/opt_*.json，按 skill 規範產出報告。

規範欄位：
  單組合：Best Params / IS Sharpe / OOS Sharpe / Win Rate / Profit Factor /
          Max DD / 交易次數
  MC：期望年化收益 / 95% VaR / 破產機率
  文字解讀：必須包含（OOS<0 要明確警示）
"""
import json, glob, os, sys

def find_latest(pattern):
    fs = glob.glob(f'/root/Crypto-Backtesting-Lab/backtest_history/{pattern}')
    if not fs: return None
    return max(fs, key=os.path.getmtime)

def g(d, *keys, default='—'):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            d = d[k]
        else:
            return default
    return d

def fmt(v, p=3, suf=''):
    if v == '—' or v is None: return '—'
    try:
        return f"{float(v):.{p}f}{suf}"
    except (TypeError, ValueError):
        return str(v)

def report(path):
    with open(path) as f:
        d = json.load(f)
    print(f"檔案: {os.path.basename(path)}")
    print(f"策略: {g(d,'strategy','name','strategy_name')}  "
          f"標的: {g(d,'symbol','meta','symbol')}  週期: {g(d,'timeframe','tf','meta','tf')}")
    print()

    # 最佳參數
    bp = d.get('best_params') or d.get('params') or {}
    print("Best Params:")
    if isinstance(bp, dict):
        for k, v in bp.items():
            print(f"  {k:16s} = {v}")
    else:
        print(f"  {bp}")
    print()

    # 指標（欄位名可能有多種變體）
    is_s = d.get('is_sharpe') or d.get('sharpe_ratio') or d.get('metrics',{}).get('sharpe_ratio')
    oos = d.get('oos_sharpe') or d.get('wf',{}).get('oos_sharpe') or \
          d.get('walk_forward',{}).get('oos_sharpe')
    wr = d.get('win_rate') or d.get('metrics',{}).get('win_rate')
    pf = d.get('profit_factor') or d.get('metrics',{}).get('profit_factor')
    dd = d.get('max_drawdown_pct') or d.get('max_drawdown') or d.get('metrics',{}).get('max_drawdown_pct')
    nt = d.get('total_trades') or d.get('n_trades') or d.get('metrics',{}).get('total_trades')
    ret = d.get('total_return_pct') or d.get('metrics',{}).get('total_return_pct')

    print("績效:")
    print(f"  IS Sharpe      : {fmt(is_s)}")
    print(f"  OOS Sharpe     : {fmt(oos)}")
    print(f"  Win Rate       : {fmt(wr,1,'%') if isinstance(wr,(int,float)) and wr<=1 else fmt(wr,1)}")
    print(f"  Profit Factor  : {fmt(pf,2)}")
    print(f"  Max DD         : {fmt(dd,2,'%')}")
    print(f"  交易次數        : {nt if nt!='—' else '—'}")
    print(f"  總報酬          : {fmt(ret,2,'%')}")
    print()

    # WF 細節
    wf = d.get('walk_forward') or d.get('wf') or {}
    if wf:
        print("Walk-Forward:")
        wins = wf.get('windows') or wf.get('folds') or []
        if isinstance(wins, list) and wins:
            for i, w in enumerate(wins, 1):
                print(f"  fold {i}: IS {fmt(w.get('is_sharpe'))} → OOS {fmt(w.get('oos_sharpe'))}"
                      f"  {'(fallback)' if w.get('used_fallback') else ''}")
        for k in ('oos_sharpe_mean','oos_sharpe_std','n_windows','used_fallback'):
            if k in wf: print(f"  {k}: {wf[k]}")
        print()

    # MC
    mc = d.get('monte_carlo') or d.get('mc') or {}
    if mc:
        print("Monte Carlo:")
        for k in ('expected_annual_return','annual_return','mean_return',
                  'var_95','var_95_pct','max_drawdown_95','ruin_probability',
                  'probability_of_ruin','n_simulations'):
            if k in mc: print(f"  {k:26s}: {mc[k]}")
        print()

    # 文字解讀
    print("解讀:")
    try:
        o = float(oos) if oos != '—' else None
        i_ = float(is_s) if is_s != '—' else None
    except (TypeError, ValueError):
        o = i_ = None
    if o is not None:
        if o < 0:
            print("  ⚠️ 樣本外失效（OOS Sharpe < 0）— 不建議實盤")
        elif i_ is not None and i_ > 0:
            drop = (i_ - o) / i_ * 100 if i_ else 0
            if drop > 50:
                print(f"  ⚠️ IS/OOS 落差 {drop:.0f}% — 高度疑似過擬合")
            else:
                print(f"  OOS 仍有正 Sharpe ({o:.2f})，IS/OOS 落差 {drop:.0f}% — 穩健性需再驗")
    else:
        print("  （無 OOS 數據，無法判斷穩健性）")

if __name__ == '__main__':
    pats = sys.argv[1:] or ['opt_breakout_5m_long*.json']
    found = False
    for p in pats:
        files = sorted(glob.glob(f'/root/Crypto-Backtesting-Lab/backtest_history/{p}'),
                       key=os.path.getmtime, reverse=True)
        for f in files[:3]:
            report(f)
            print("=" * 62)
            found = True
    if not found:
        print(f"找不到符合的 opt 檔案: {pats}")
        print("（表示優化尚未完成，或檔名模式不符）")
