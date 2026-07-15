# Research 模組設計規格（Design Spec）

> 來源：`docs/research/2026-07-15-research-phase1.md`（Phase 1 Research 已批准）
> 批准決策：**A+B 範圍**（市場研究 + 輕量策略信號層）、推薦指標集、沿用 in-memory 任務模式
> 日期：2026-07-15　狀態：Design（待實作計畫）

---

## 1. 範圍（Scope）

**A. 市場研究 Market Research（核心）**
對標的裸 K 線做統計探索，回答「該不該做回測 / 用什麼週期 / 什麼波動環境」。
首版指標集：
1. `returns_stats` — 對數報酬均值/標準差/偏度/峰度/年化波動
2. `autocorrelation` — lag=1..N 自相關（動量/反轉判讀）
3. `hurst` — Hurst 指數（<0.5 均值回歸 / >0.5 趨勢）
4. `vol_regime` — 波動率聚类（GARCH 式滾動 std 分位，標記 high/low regime 區間）
5. `correlation` — 與 BTC/USDT 滾動相關（判斷分散性）
6. `seasonality` — 星期效應（各 weekday 平均報酬）

**B. 策略信號層 Strategy Signal Layer（輕量，phase 2 內含）**
不跑完整 P&L，僅跑 `StrategyBase.next()` 產生信號序列，輸出：
- 信號分布（buy/sell/close 次數、多空比）
- 進場時點統計（信號觸發時的 RSI/價格分位）
- 與 buy&hold 進場點對比（重疊率）
- 信號後 N 根平均報酬（信號邊際資訊含量初探）

**非目標（YAGNI）**：不重複 Analysis 的 Walk-Forward/Monte-Carlo；不接 Redis；不做 ML 特徵工程（StrategyBase.predict 預留，不在本 spec）。

---

## 2. 後端設計

### 2.1 `engine/research.py`（純函數，pandas 輸入）
```python
def market_profile(df: pd.DataFrame, benchmark: pd.DataFrame | None = None) -> dict:
    """A: 回傳 returns_stats/autocorrelation/hurst/vol_regime/correlation/seasonality"""
def signal_profile(df: pd.DataFrame, strategy_cls, params: dict) -> dict:
    """B: 回傳信號分布 + 時點統計 + 信號後報酬"""
```
- 複用 `from engine.backtester import Backtester; Backtester._sharpe(returns)` 避免重造。
- 全為確定性函數，便於 pytest。

### 2.2 `app/services/research_service.py`
- 沿用 `data_service.py` 的 `_analysis_tasks` in-memory 模式（`{task_id: {status, result/error}}`）。
- `run_market_research(config)` / `run_signal_research(config)` → 回傳 `{task_id, status:"running"}`，`asyncio.create_task` 執行。
- 內部：`await self.data_service.get_ohlcv(symbol, tf, start, end, source)` 取數 → 調 `engine.research` → 存結果。

### 2.3 `app/api/routes/research.py`
```
POST /api/research/run          body: {type:"market"|"signal", symbol, timeframe, start_date, end_date, source?, metrics?, strategy_id?, params?}
                                -> {task_id, status}
GET  /api/research/results/{id} -> {task_id, status, summary:{...}}
```
- 註冊進 `app/main.py` 的 router 聚合（與 analysis/backtest 同款）。

## 3. 前端設計

### 3.1 路由與導航
- 新增 `frontend/src/app/research/page.tsx`（沿用 `PageShell` + `Card` + `Metric` + `Spinner`，仿 `analysis/page.tsx`）。
- `frontend/src/components/layout/Header.tsx` 的 `navItems` 加 `{ name: 'Research', path: '/research', icon: FlaskConical }`。

### 3.2 狀態與類型
- `frontend/src/types/api.ts` 加 `ResearchResult` interface（對齊 summary 結構）。
- `frontend/src/lib/api.ts` 加 `runResearch(cfg)` / `getResearchResults(id)`。
- 新增 `frontend/src/stores/useResearchStore.ts`（Zustand）：`config / status / result / error / runResearch() / poll()`。

### 3.3 頁面佈局
- 頂部 `PageShell eyebrow="Research / explore"` `title="市場與策略研究"`。
- 控制列：標的選擇（複用 `useDataStore.loadSymbols` + `SymbolSearch`）、週期 Select、研究類型 Tab（Market / Signal）、Signal 模式下顯示策略 Select（`getTemplates`）。
- 結果區：`market` → 6 張 Metric 卡 + 波動 regime 區間標註；`signal` → 信號分布條 + 時點統計表。
- 輪詢：`setInterval` 每 1s 查 `getResearchResults`，completed/error 停止（仿 analysis）。

## 4. 數據流圖
```
[UI] research/page -> useResearchStore.runResearch()
  -> api.runResearch() POST /api/research/run
  -> research_service.run_market/signal_research()  (asyncio task)
       -> DataService.get_ohlcv(symbol,tf,start,end,source)  [複用 + 快取]
       -> engine.research.market_profile / signal_profile
       -> _analysis_tasks[task_id] = {status, result}
  <- {task_id}
[UI] poll GET /api/research/results/{id} -> summary
```

## 5. 錯誤處理
- `get_ohlcv` 回空 → `_analysis_tasks[task_id] = {status:"error", error:"No data available"}`。
- 引擎異常 → `status:"error"` + `str(e)`，前端顯示紅字（仿 analysis 的 error 分支）。
- 標的/週期非法 → Pydantic 422 由 FastAPI 自動回傳。

## 6. 測試
- 後端單元：`engine/research.py` 用 `data/providers/test_data.generate_test_data` 造數，斷言 `market_profile` 回傳 6 鍵、`hurst` ∈ (0,1)、`signal_profile` 信號計數匹配 `StrategyBase` 實際觸發。
- 路由整合：`TestClient` POST `/api/research/run` → 輪詢 `results/{id}` 到 completed。
- 前端：`tsc --noEmit` 通過（現有 CI 慣例）；手動跑 BTC/USDT 1h market research 驗證畫面。

## 7. 驗收標準
1. `/research` 頁可選標的+週期，跑 Market Research 回傳 6 項統計且數值合理。
2. Signal 模式選策略後回傳信號分布 + 時點統計。
3. 錯誤路徑（空數據/非法輸入）有明確提示，不崩潰。
4. 新增文件不破壞現有 pytest（97 passed）+ 前端 build。
5. 部署後 Railway + Vercel 實測通過。

<!--END-->
