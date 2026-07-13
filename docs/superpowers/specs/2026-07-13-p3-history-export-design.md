# P3 — Backtest 歷史記錄與結果匯出設計

日期：2026-07-13
範圍：backtest 結果持久化（git + 檔案）、history 端點 + 頁面、CSV 匯出（純前端）。
P1（optimize 頁）、P2（data 頁）已完成並部署。本批不動 optimize/data 頁。

## 背景與現狀

- 後端 `_backtest_tasks` 為 in-memory dict（`app/services/data_service.py`），Railway 重啟後清空，且無 `/history` 端點。
- 現有持久化模式：`app/services/strategy_git.py` 的 `git_persist([files], msg)` 用 `GITHUB_TOKEN` commit + push 到 master（strategies 上傳已用）。可複用。
- `BacktestResultOut`：task_id, status, metrics(MetricsOut), equity_curve:list[float], trades:list[TradeRecord]。
- `TradeRecord` 含 pnl/pnl_pct/entry/exit 等；`EquityPoint` 含 timestamp/equity。
- 前端 backtest 頁已有完整結果 UI（MetricsCard / EquityCurve / DrawdownChart / Trade Blotter），但無「儲存/歷史/匯出」。
- 前端無任何 download/CSV 機制。

## 設計決策（用戶選 B = 持久化）

### P3a：持久化歷史
1. **寫入**：在 `_execute_backtest` 完成分支（status='completed'），將結果 + 原始 config 序列化為 `backtests/{task_id}.json`，呼叫 `git_persist([path], "feat(backtest): save {task_id}")`。
   - JSON 結構：`{task_id, status, created_at, config, metrics, equity_curve, trades, equity_points?}`。
   - `created_at` 用 `datetime.utcnow().isoformat()`。
   - config 需從 store 取（backtest run 時存的 config）。若 store 無 config，至少在 JSON 存 task_id/status/metrics/trades/equity_curve。
2. **history 端點**：`GET /api/backtest/history` → 掃 `backtests/*.json`，回 `[{task_id, status, created_at, strategy, symbol, timeframe, sharpe}]`（sharpe 從 metrics 取）。按 created_at 降序。
3. **結果讀取（重啟後仍可讀）**：`GET /api/backtest/results/{task_id}` 現從 `_backtest_tasks` 讀；增加 fallback：若 in-memory 無，則從 `backtests/{task_id}.json` 讀檔回傳（保持 `BacktestResultOut` schema）。這樣 Railway 重啟後 history 仍可點開。
4. **前端 history 頁** `frontend/src/app/history/page.tsx`：
   - 載入 `/api/backtest/history`，列表（task_id 縮寫、策略、symbol、sharpe、時間）。
   - 點擊項目 → 呼叫 `/api/backtest/results/{task_id}` → 把結果塞進 backtest store 的 `results`（或導航到 `/backtest?task_id=xxx` 並自動 load）。**採用前者較簡**：history 頁點擊後直接顯示該次結果（複用 MetricsCard/EquityCurve，或導向 backtest 頁並帶 task_id query）。
   - 簡化：history 頁點擊 → `router.push('/backtest?task='+task_id)`，backtest 頁 `useEffect` 讀 `?task=` → 呼叫 `getBacktestResults(task)` 填入 store。
5. **nav**：Header 加 History 連結。

### P3b：CSV 匯出（純前端，不動後端）
6. 在 backtest 結果區加「Export CSV」按鈕（`Button variant="ghost"`）。
   - 匯出內容：trades 表（entry/exit/pnl/pnl_pct/size/...）+ equity_curve。
   - 實作：client-side 把 `results.trades` 與 `results.equity_curve` 轉 CSV 字串 → `Blob` → `URL.createObjectURL` → `<a download>` 觸發。
   - 不經後端，無網路成本。

## 技術約約
- 複用 `git_persist`（已有 GITHUB_TOKEN 環境變數；Railway 需確認 GITHUB_TOKEN 已設——若無則 git_persist 回傳 False 並 log warning，不阻塞 backtest）。
- `backtests/` 目錄需建立（放 `.gitkeep` 或首次寫入時 `Path.mkdir(parents=True, exist_ok=True)`）。
- history 端點掃檔用 `glob.glob("backtests/*.json")`，無則回 `[]`。
- CSV 匯出為 client component 內函式，不引新依賴。
- 風格與 P1/P2 一致（borderless / mono / dark-light adaptive）。

## 驗證
- `cd frontend && npm run build` exit 0。
- 後端：`run_backtest` 完成後 `backtests/{task_id}.json` 出現 + git push（若 token 在）。
- `/api/backtest/history` 回非空的陣列。
- `/api/backtest/results/{task_id}` 重啟 Railway 後仍能從 JSON 讀（模擬：重啟後舊 task_id 仍可讀）。
- 前端 `/history` 頁列出 + 點擊導向 backtest 帶結果；Export CSV 下載檔案。
- Vercel 部署後 custom domain 通。

## 不在本批
- P4（首頁 dashboard / 多用戶）。
- 不引 DB / Redis（git 檔案持久化已滿足 B）。
- 不修改 optimize/data 頁。
