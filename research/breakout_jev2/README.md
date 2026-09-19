# 5m 突破 × Jev × 蒙地卡羅（第二輪，2026-09-20）

## 目標
回答一個是非題：5m 突破策略在扣除成本後，**是否存在足以支撐「月化 20%（複利）、加槓桿後回撤 <= 30%」的 edge**。

## 結論：**不存在**（與第一輪 `research/breakout_jev/` 獨立驗證後一致）

兩輪研究方法與樣本**刻意不同**，結論相同 → 可信度高。

| 檢驗 | 結果 |
|---|---|
| 原始 edge（零成本 95% CI） | 25 個配置中 **顯著為正 0 個、顯著為負 4 個**（突破在 APT/SUI/BCH 上是**反指標**） |
| 錨定式 Walk-Forward（含隨機參數對照） | 所有標的 OOS 平均為正：**否**（BTC -3.75、APT -9.03、FIL -0.73、BCH -8.83） |
| OOS 勝過 control P90 且樣本 >= 20 筆 | **0 折**（3 折帳面勝出但樣本 < 20，無效） |
| 蒙地卡羅（10,000 次 × 20 配置） | 達月化 20% 機率 **全為 0.0%**；無任何配置回撤 < 30% |
| Jev 過濾器（嚴格 OOS） | 4/5 標的準確率**恰等於多數類基準線** → 零技能 |

## 月化 20% 的數學門檻（為什麼不可能）

- 目標月化 20% ⇒ 100 筆/月、賠率 1.5 下，每筆需淨 **+1.67%**
- 實測：零成本每筆 −0.02% ~ +0.18%（多數為負）；扣 0.14% 來回成本後幾乎全負
- **差 1~2 個數量級**。且 FIL 就算用最樂觀的 +0.0368%/筆，也需 35,240 筆（實測 69 筆）
- 槓桿是放大鏡不是引擎：BTC 1x 中位月化 −2.17% → 10x −22.06%（線性放大虧損）

## 本輪方法論修正（相對第一輪的四項）

1. **蒙地卡羅自寫**，不用 `engine/analyzer.MonteCarloSimulator`
   它按 bar 當一天（5m 資料 252 步 = 21 小時），且無破產/槓桿/爆倉概念 → 對本題完全失真。
   自寫版用 **per-trade 報酬**重抽樣 + 槓桿線性套用 + 爆倉歸零 + MaxDD P95 / 破產機率。
2. **Walk-Forward 改錨定式（anchored）+ 隨機參數 control**
   第一輪用滾動窗（重疊 83% 污染）且無 control → 無法分辨「最佳參數 OOS」是否只是運氣。
   本輪：IS 固定從 index 0 起、每折 OOS 互不重疊，並用 R=20 隨機參數組當對照。
3. **槓桿與爆倉顯式建模**（先前完全沒有）
   `ret = L*gross - 2*fee*L`、`liq_px = entry*(1 - (1/L - 0.005))`，爆倉歸零。
4. **Jev 從「逐棒決策核心」改成「離線訓練的過濾器」**
   第一輪已證逐棒不可行（每棒 5.3s、state 批次污染、模型無法 pin）。
   本輪協定：train 50%（擬合門檻）→ val 25%（選門檻）→ test 25%（只跑一次），
   state 只放單根棒、中性零引導提問、成本計入（總 842,107 tokens = $0.0354）。

## 工程失敗教訓（本輪新學到，重要）

1. **特徵欄位必須按參數分別儲存，否則參數形同虛設**
   `add_features()` 原本只產生單一 `don_hi`（固定 lookback=720），而 `backtest()` 讀的是
   `df["don_hi"]` → **所有 lookback 跑出完全相同的結果**（第一次跑出 5 個 lookback 數字一字不差，
   才發現）。修法：`don_hi_<n>` per-lookback 欄位，`backtest()` 依參數選欄位，並加回歸測試
   `test_lookback_selects_matching_channel_column`。
   → **判讀訊號：不同參數跑出相同數字 = 參數沒接進去，不是「市場穩定」。**
2. **回撤符號慣例要先確認再寫判定**
   `mc_summary` 的 `maxdd_*_pct` 是**正值**（回撤幅度），判定寫成 `> -30` 導致 FIL 1x 被誤判「可用」
   （實際 53.7% 回撤）。修法：`< MAX_DD_PCT`。
   → **判定式與資料單位/符號必須寫在同一段程式碼旁邊，不要分開。**
3. **測試 fixture 的預設值要「不觸發」，否則測不到想測的東西**
   fixture 原本 `don_hi=99` 每根都成立 → 每根都發訊號，`test_no_signal_no_trades` 假失敗。
   修法：預設 `don_hi=999`（不觸發），要測訊號的測試自行改特定 bar。
4. **「勝過對照組」必須同時看樣本量**
   SUI 有 2 折 OOS Sharpe > control P90，但樣本只有 n=13 與 **n=2** —— 統計上無效。
   `beats_control` 必須加 `oos_n >= 20` 門檻，否則會給出假的正面結論。

## 檔案

```
research/breakout_jev2/
  make_5m_csv.py         1m parquet -> 5m CSV（gridlab 來源）
  lib_data.py            載入 + ATR + 每 lookback 的 Donchian 通道（無未來函數）
  lib_backtest.py        回測核心：per-trade 報酬、費用、滑價、槓桿、爆倉、資金費率、load_env()
  lib_stats.py           bootstrap CI、蒙地卡羅、必要樣本量
  s1_edge.py             Stage 1 原始 edge（閘門）
  s2_walkforward.py      Stage 2 錨定式 WF + 隨機參數對照
  s3_monte_carlo.py      Stage 3 MC（槓桿/爆倉/月化 20% 機率）
  s4_jev_gate.py         Stage 4 Jev 過濾器（嚴格 OOS）
  report.py              彙整報告產生器
  README.md              本檔
tests/                   test_make_5m_csv / test_lib_data / test_lib_backtest / test_lib_stats（17 passed）
runtime/breakout_jev2/   s1~s4 JSON + REPORT.md（gitignored）
```

重跑：
```bash
cd /root/Crypto-Backtesting-Lab
./venv/bin/python -m pytest tests/ -q                       # 17 passed
./venv/bin/python -m research.breakout_jev2.make_5m_csv
./venv/bin/python -m research.breakout_jev2.s1_edge
./venv/bin/python -m research.breakout_jev2.s2_walkforward
./venv/bin/python -m research.breakout_jev2.s3_monte_carlo
./venv/bin/python -m research.breakout_jev2.s4_jev_gate
./venv/bin/python -m research.breakout_jev2.report > runtime/breakout_jev2/REPORT.md
```

## 已知缺口（不可假裝有）

- **資金費率**：perp 持倉需付/收 funding，本輪只有參數介面（`funding_per_8h`），未取得真實費率資料。
- **流動性**：滑價固定 0.02%/邊，低流動性標的（SUI/APT/BCH）實際更差。
- **槓桿路徑簡化**：事後線性套用 + 爆倉歸零，不含追繳減倉的動態路徑。
- **5m 資料僅 10~33 個月**，年化數字樣本量薄弱。

## 下一步（若仍要繼續）

唯一有結構性理由的改變是**換時間框架**：1h 的 ATR% 約 0.5%（5m 的 0.14% 的 3.5 倍），
成本佔比低一個數量級、競爭密度低。**但那是另一個題目，且不保證可行** ——
本輪的 1h 對照組（`research/` 其他回測）同樣未通過 OOS。

**不建議**：在 5m 上加槓桿、擴大參數網格、或再測別的 Jev 問法。已證訊號本身為零，
任何濾網都只能在負期望值上做選擇。
