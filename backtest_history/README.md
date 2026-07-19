# 永久回測紀錄 (git 跟踪)

此目錄存放「有價值、需永久保存」的回測結果 JSON。
來源：網站 /backtest/run 跑完後從 Railway 拉回，或本地 backtests/ 複製。

## 檔案
- `combo_KCxVolZ_2026-07-19.json` — KC突破+量異常, 網站回測: 4筆/-0.53%/MDD-3.43%/Sharpe-1.11
- `combo_IchxVolZ_2026-07-19.json` — Ichimoku雲+量異常, 網站回測: 54筆/勝率62.96%/+19.67%/MDD-10.99%/Sharpe0.31 ★

## 對應策略代碼
- `strategies/combo_KCxVolZ.py`
- `strategies/combo_IchxVolZ.py`

## 挖掘來源
- `research/combo_findings.md` — 20輪指標組合挖掘記錄
- `research/combo_explorer.py` — 挖掘腳本
