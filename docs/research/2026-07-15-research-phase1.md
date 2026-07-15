# Phase 1: Research — 需求分析與實作評估

> 目的：掃描現有專案，找出 Research 功能的依據、最佳實作路徑，產出可執行的設計前研究文檔。
> 日期：2026-07-15　狀態：Phase 1 Research（設計前）

---

## 1. 掃描發現（專案現狀證據）

現有平台是一套「策略回測 → 優化 → 穩健性分析」的工作流，技術棧為 FastAPI + Next.js 14。

**功能模組（後端 `app/api/routes/`）**
- `backtest.py` — `/run` `/status/{id}` `/results/{id}` `/history`
- `optimize.py` — `/run` `/results/{id}` `/best-params`
- `analysis.py` — `/walk-forward` `/monte-carlo` `/results/{id}`
- `strategy.py` — `/validate` `/templates` `/upload` `/user`
- `data.py` — `/symbols` `/ohlcv` `/import`
- `arbitrage.py` — `/run`
- `monitoring.py` — `/push` `/stats`

**前端路由（`frontend/src/app/`）**
`/backtest` `/optimize` `/analysis` `/arbitrage` `/data` `/strategies` `/history`
導航列 `Header.tsx`：Backtest / Optimize / Analysis / Arbitrage。**無 Research。**

**引擎層（`engine/`）**
- `backtester.py` — `BacktestResult` 含 20+ 指標（sharpe/sortino/calmar/profit_factor/win_rate/avg_winner/avg_loser…）+ equity_curve + trades。
- `analyzer.py` — `WalkForwardAnalyzer` / `MonteCarloSimulator`（樣本外驗證 + 破產機率）。
- `optimizer.py` — grid / bayesian（Optuna）。
- `arbitrage.py` — 價差統計套利。
- **不存在** 任何獨立的統計/市場研究原語（無 correlation / hurst / regime / distribution / seasonality 函數）。

**數據層（`data/providers/`）**
- `bingx.py`（合約，含 NCCO* 貴金屬/商品）/ `binance.py` / `tradfi.py`（Yahoo 股票/股指/外匯/貴金屬）/ `csv_loader.py` / `test_data.py`。
- `DataService.get_ohlcv(symbol, tf, start, end, source)` 已支援多源路由 + 快取，可為 Research 直接複用。

**指標庫**
- `BacktestResult` 已計算 sharpe/sortino/calmar，但**只在回測後**才產生，無法在回測前對裸 K 線做統計。
- 無獨立 `metrics.py` 暴露給「不跑策略、只分析數據」的流程。

**結論**：Research 是全新前回測（pre-backtest）探索層，專案已有 80% 基礎設施可複用（數據路由、任務模式、前端骨架），缺口在「統計研究原語」與「Research 頁/路由」本身。

## 2. Research 功能範圍定義（需用戶確認的關鍵決策）

「Research」在量化平台常指兩種不同的事，這決定整個實作方向：

| 取向 | 定義 | 輸出 | 與現有模組關係 |
|---|---|---|---|
| **A. 市場研究 Market Research** | 對標的裸 K 線做統計探索，決定「該不該/用什麼週期/什麼波動環境做回測」 | 波動率分佈、回報自相關、Hurst 指數、趨勢/震盪 regime、季節性、與 BTC 相關性、流動性/缺口分析 | 回測前哨，獨立於策略 |
| **B. 策略研究 Strategy Research** | 對單一策略做參數敏感度/假設檢驗，決定「這策略邏輯是否成立」 | 參數平原熱圖、信號分布、進出場時點統計、與 buy&hold 對比、多標的泛化 | 回測的淺層版（不跑完整 P&L，只跑信號） |

**推薦：先做 A（市場研究）+ 輕量 B 的信號層**，因為：
1. 用戶是「先看市場再決定策略」的實盤交易者（SOUL.md：數據天賦 × 策略思維）。
2. A 完全複用 `DataService.get_ohlcv`，只需新增統計原語 + 一個 `/api/research/*` + `/research` 頁。
3. B 的信號層可複用 `StrategyBase.next()` 但不跑 P&L，成本極低。

> ⚠️ **此決定影響後續所有設計**。請確認走 A / B / A+B。

## 3. 實作路徑評估（3 方案 + 推薦）

### 方案 1：引擎層新增 `engine/research.py` + `/api/research` 路由（推薦）
- **做法**：新增 `engine/research.py` 提供統計原語（`returns_stats`, `autocorrelation`, `hurst`, `volatility_regime`, `seasonality`, `correlation`）；新增 `app/services/research_service.py`（沿用 `_analysis_tasks` 同款 in-memory 任務模式）；新增 `app/api/routes/research.py`（`/run`, `/results/{id}`）；前端 `frontend/src/app/research/page.tsx` + `Header.tsx` 加 nav + `types/api.ts` 加 `ResearchResult`。
- **優**：完全符合既有架構慣例（analysis/backtest 都是 route+service+engine+page+store+types 六件套）；可複用 `DataService.get_ohlcv` + 快取；與 Analysis 模組對稱，未來易擴充。
- **劣**：需新增約 6 個文件，前端工作量中等。
- **適用**：A / B / A+B 皆可。

### 方案 2：擴充既有 `/analysis` 路由，加 `market_research` 協議
- **做法**：在 `analysis_service.py` 加 `run_market_research()`，frontend `analysis/page.tsx` 加第三個 tab。
- **優**：不新增路由/頁面，最快。
- **劣**：語意混淆（Analysis 是「策略穩健性」，Research 是「市場探索」）；`analysis.py` 路由與前端會膨脹；違反「每功能一個清晰單元」原則（brainstorming skill 強調）。
- **適用**：僅當明確只要最小可行、不在意架構清晰度。

### 方案 3：獨立微服務 / 外接 notebook
- **做法**：Research 用獨立 Python 服務或 Jupyter。
- **優**：隔離重計算。
- **劣**：與現有 FastAPI 單體、Zustand 狀態、部署（Railway 單容器）格格不入；過度工程（ponytail 原則禁止）。
- **適用**：僅當研究計算需 GPU/超大數據。

### ✅ 推薦：方案 1
符合專案既有「六件套」慣例、ponytail 最簡有效、且為未來擴充留接口。先做 A 範圍（市場研究），B 的信號層作為 phase 2。

## 4. 建議介面草圖（方案 1，A 範圍）

**後端 `engine/research.py`（純函數，pandas 輸入）**
```python
def market_profile(df: pd.DataFrame) -> dict:
    # returns_stats / autocorrelation(lag) / hurst / vol_regime / seasonality / correlation_to(BTC)
    ...
```

**後端 `app/api/routes/research.py`**
```
POST /api/research/run        { symbol, timeframe, start_date, end_date, metrics:[...] } -> {task_id}
GET  /api/research/results/{id} -> { task_id, status, summary:{...} }
```

**前端 `research/page.tsx`**：沿用 `PageShell` + `Card` + `Metric` 元件（analysis/page.tsx 已示範），標的/週期選擇複用 `useDataStore.loadSymbols` + `SymbolSearch`。

**複用清單（避免重造）**
- `DataService.get_ohlcv` — 數據 + 多源 + 快取 ✅
- `engine/backtester.py::_sharpe` — 可直接 import 複用 ✅
- `_analysis_tasks` in-memory 模式 — 任務狀態 ✅
- `Header.tsx` navItems — 加一項 `Research` ✅
- `PageShell / Card / Metric / Spinner` — UI 元件 ✅

## 5. 證據索引（掃描依據）
- 後端路由：`app/api/routes/{backtest,optimize,analysis,strategy,data,arbitrage,monitoring}.py`
- 引擎：`engine/{backtester,analyzer,optimizer,arbitrage}.py`（無統計研究原語）
- 數據：`data/providers/{bingx,binance,tradfi,csv_loader}.py` + `app/services/data_service.py`
- 前端：`frontend/src/app/*`、`components/layout/Header.tsx`、`components/layout/PageShell.tsx`、`app/analysis/page.tsx`、`types/api.ts`
- 架構：`docs/ARCHITECTURE.md`（六件套慣例、Zustand stores、API client 層）

## 6. 待確認事項（Phase 1 → 設計門檻）
1. **範圍**：A 市場研究 / B 策略研究 / A+B？（推薦 A + 輕量 B 信號層）
2. **指標集**：首版要哪些？（推薦：波动率分布、Hurst、自相关、regime、与 BTC 相关性、seasonality）
3. **任務模式**：沿用 in-memory `_analysis_tasks`（與現狀一致，Railway 單 worker）即可，還是要接 Redis？

## 7. 下一步
確認 §6 後，進入 brainstorming 設計門檻 → 寫 `docs/superpowers/specs/...-design.md` → `writing-plans` 產出實作計畫。

<!--END-->
