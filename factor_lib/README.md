# Factor Library / 因子庫

回測結果台的特徵層。三個來源，按「單標的時間序列」(BTC_USDT_1h 等 OHLCV) 適配。

## 結構

```
factor_lib/
├── alpha101_src/          # lvlh2/alpha101 克隆 (Alphas class, 橫截面設計)
├── alpha101_worldquant/   # yli188/WorldQuant_alpha101_code (101Alpha_code_1/2.py, 純函數)
├── pandas_ta_features/    # ✅ 已產出: 每 CSV 130+ 技術指標矩陣 (.parquet)
├── qlib_factors/          # qlib Alpha158/360 文檔抽取 (qlib_loader_source.py)
├── awesome_quant_ref/     # wilsonfreitas/awesome-quant 克隆 (量化工具索引, 非因子庫)
└── factor_pandas_ta.py    # ✅ pandas_ta 批量計算腳本 (單標的直接適配)
```

## 已可用 (A 方案)

### pandas_ta 特徵矩陣
- 腳本: `factor_lib/factor_pandas_ta.py`
- 輸出: `factor_lib/pandas_ta_features/<SYM>_<TF>.parquet`
- 覆蓋: 274 因子列 (BTC 1h 實測), 93.6% 非空缺蓋率
- 用法:
  ```bash
  source /root/ytvenv/bin/activate
  python3 factor_lib/factor_pandas_ta.py              # 全部 CSV
  python3 factor_lib/factor_pandas_ta.py --symbol BTC_USDT --tf 1h  # 單檔
  ```
- 依賴: pandas_ta 0.4.71b0 (numpy 2.2.6)
- 注意: 部分指標需 TA-Lib (unique3river 等) 或 DatetimeIndex (VWAP/Pivots)，自動跳過

## 待適配 (B 方案 - 睡前未做)

### Alpha101 時序改寫
- 源碼已克隆 (alpha101_src / alpha101_worldquant)
- 問題: 原版是**橫截面**設計 (groupby('date').rank() 跨多標的), 對單標的失效
- 計劃: 把 101 公式的橫截面操作改為 rolling 時序版 (rank→rolling rank, corr across assets→rolling corr)
- 約 80/101 可純時序化, 其餘標註需橫截面

## 僅存文檔 (C 方案 - 按用戶決定)

### Qlib Alpha158 / Alpha360
- `qlib 0.9.7` 已裝 (pyqlib), 但**污染主 venv**: 把 pandas 3.0.3 → 2.3.3
- ⚠️ 風險: 現有回測引擎 (1195 opt 結果) 跑在 pandas 3.0, 環境被改可能影響重現性
- 決策: qlib 不進主環境, 應移動到獨立 venv 隔離 (待用戶醒後執行)
- 公式文檔: `qlib_factors/qlib_loader_source.py` (從 qlib 源碼抽取 Alpha158 定義)

### awesome-quant
- 資源清單 (curated links), 非因子計算庫
- 用途: 量化工具/因子分析庫索引, 存檔參考
- 路徑: `factor_lib/awesome_quant_ref/`

## 環境坑 (記錄)
- pandas_ta 0.4.71b0: 無 Strategy API, 改用單指標迴圈 (df.ta.<ind>(append=False))
- qlib 0.9.7: 凍結 pandas<2.4, 裝後主環境 pandas 降版 → 需隔離 venv
- numpy: pandas_ta 裝時降到 2.2.6, qlib 再降到 2.2.x 兼容

## Next (用戶醒後)
1. 隔離 qlib 到獨立 venv (uv venv / venv), 恢復主環境 pandas 3.0
2. 實作 Alpha101 時序改寫版 (factor_alpha101_ts.py)
3. 批量跑 pandas_ta 全 11 幣 × 5 週期 (目前只跑部分)
4. 因子矩陣接回回測引擎 (作為策略特徵輸入)
