# Research Module — Goal

> 來源：docs/research/2026-07-15-research-phase1.md（Phase 1 研究）
> 日期：2026-07-15　狀態：LIVE（已 merge + 部署 + 實測通過）

## Objective
為量化回測平台建立**回測前探索層（pre-backtest exploration）**：在跑策略之前，先對裸 K 線與策略信號做統計畫像，決定「該不該回測 / 用什麼週期 / 什麼波動環境 / 這策略邏輯是否成立」。

## Scope（採 A + B，經用戶批準「照你說的」）

### A. 市場研究 Market Research
對標的裸 OHLCV 做統計探索，輸出決策依據：
- `returns_stats` — 年化波動、偏態、峰態
- `autocorrelation` — lag-1 回報自相關
- `hurst` — 長期記憶（趨勢/均值回歸）
- `vol_regime` — 波動率 regime
- `correlation` — 與 BTC/USDT 相關性（非 BTC 標的才取 benchmark）
- `seasonality` — 星期效應（各 dow 平均回報）

### B. 輕量策略研究 Strategy Research（信號層，不跑 P&L）
對單一策略複用 `StrategyBase.next()` 只跑信號：
- `signal_counts` — 動作分布（buy/sell/close）
- `long_short_ratio` — 多/空開倉比（longs/shorts，真 ratio）
- `entry_timing` — 進場價在當時 50-bar 區間的百分位 + 樣本數
- `signal_forward_return` — 信號後 N=5 根 forward return 均值 + n

## Success Criteria（對應 research.md §3 方案 1）
- [x] `engine/research.py` 純 pandas 統計原語（market_profile + signal_profile）
- [x] `app/services/research_service.py` 沿用 `_analysis_tasks` in-memory 任務模式
- [x] `app/api/routes/research.py`：`POST /api/research/run` + `GET /api/research/results/{id}`
- [x] 前端 `/research` 頁（市場 + 信號雙模式）+ `Header.tsx` nav + `types/api.ts` + `useResearchStore`
- [x] 複用 `DataService.get_ohlcv`（多源 + 快取）、`get_strategy` 註冊表

## 已交付狀態（2026-07-15）
- master `fccdd98` 已 push origin（fast-forward，零衝突）
- Railway backend ✅ / Vercel `/research` ✅
- 實測：market→completed（6 keys）、signal ma_cross→completed（signal_counts {buy:103,sell:1}、long_short_ratio 103.0、entry_timing 0.707、fwd_ret -0.0048）

## 非目標（YAGNI / 延後）
- 不接 Redis（沿用 in-memory，與 Railway 單 worker 一致）
- 不跑完整 P&L（B 僅信號層）
- `correlation` 對預設 BTC/USDT 為 None（benchmark 僅非 BTC 才取）——UX 已知缺口，可接受
- 參數平原熱圖 / buy&hold 對比 / 多標的泛化 —— 留待 Phase 2

## Next（Phase 2 候選，未啟動）
- B 深化：參數敏感度、buy&hold 對比、多標的泛化
- A 深化：流動性/缺口分析、regime 切換点檢測
