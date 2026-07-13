# P2 — 數據流打通與市場數據預覽設計

日期：2026-07-13
範圍：兩部分 — (a) 統一 loading/empty 狀態組件 + 補 analysis/backtest 邊界；(b) 新 data 頁（symbols 選擇 + OHLCV 蠟燭圖預覽）。
P1（optimize 頁）已完成並部署。本批不動 optimize 頁。

## 背景與現狀

- 後端 `/api/data/symbols` (GET)、`/api/data/ohlcv` (GET, query: symbol, timeframe) 已存在且 live。
- `api.ts` 已有 `getSymbols()` / `getOHLCV(symbol, timeframe)`。
- 前端 `PriceChart` 組件（lightweight-charts candlestick）接受 `ChartData[]`，而 `ChartData extends OHLCV`（字段 timestamp/open/high/low/close/volume）——後端 `OHLCVPoint` 與之完全對應，無需轉換。
- 現有邊界狀態：backtest/analysis/strategies 頁都有 `error` 文字顯示，但**無統一 Spinner/Skeleton/EmptyState 組件**；analysis 頁 `running` 僅文字「Simulating pathways...」；backtest 頁結果區無空狀態。
- 前端導航（layout）目前有：Backtest / Analysis / Strategies / Optimize —— 缺 Data 入口。

## 設計決策

### P2a：統一狀態組件
1. **Spinner**（新文件 `frontend/src/components/ui/Spinner.tsx`）
   - SVG 旋轉圓環，尺寸 prop（`sm`|`md`|`lg`，預設 md=20px），`className` 透傳。
   - 顏色用 `currentColor`（繼承父層 text color），無硬編色。
   - 無依賴（純 SVG + tailwind animate-spin）。
2. **EmptyState**（新文件 `frontend/src/components/ui/EmptyState.tsx`）
   - props: `title: string`, `description?: string`, `icon?: ReactNode`, `action?: ReactNode`。
   - 居中、muted 文字，premium minimal 風格（無邊框卡片或純文字區）。
3. **analysis 頁**：`running` 時在 Run 鈕旁或狀態區顯示 `<Spinner />`（取代純文字或並存）。
4. **backtest 頁**：`status==='completed'` 但 `results` 為空/無 trade 時，結果區顯示 `<EmptyState title="No trades generated" description="..." />`（若有 results 則維持原圖表）。

### P2b：data 頁
5. **新頁 `frontend/src/app/data/page.tsx`**
   - 頂部 `PageShell` eyebrow="Data / market", title="市場數據預覽", subtitle 簡述。
   - 控制列：Strategy 同款 `Select` 選 symbol（從 `getSymbols()` 載入，選項 `label=symbol, value=symbol`）+ timeframe `Select`（15m/1h/4h/1d）。
   - 載入：呼叫 `api.getOHLCV(symbol, timeframe)`，loading 時顯示 `<Spinner />`，錯誤顯示 error 文字。
   - 渲染：`<PriceChart data={ohlcv} />`（ohlcv 直接是 `ChartData[]` 兼容結構）。
   - 空數據：`<EmptyState title="No data for this symbol/timeframe" />`。
   - 默認 symbol=BTC/USDT, timeframe=1h；頁面 mount 時自動載入 symbols + 預設 OHLCV。
6. **導航**：在 `frontend/src/components/layout/...` 的 nav 中加入 Data 連結（路徑 `/data`，label "Data"）。需先確認 nav 組件位置（`grep -rn "Backtest" frontend/src --include=*.tsx | grep -i nav` 定位）。

## 技術約束
- 不引新 npm 依賴（Spinner/EmptyState 純 SVG+tailwind；PriceChart 已存在）。
- 圖表數據零轉換（OHLCVPoint ↔ ChartData 字段一致）。
- data 頁為 client component（`'use client'`）。
- 與 P1 風格一致：borderless、whitespace、mono numbers、dark/light adaptive（沿用現有 tailwind tokens：`text-textSecondary`/`bg-surface`/`text-accent` 等）。

## 驗證
- `npm run build` exit 0（TypeScript 全清）。
- Vercel 部署後 `https://quant-backtest-platform-v2.vercel.app/data` 能載入 symbols 下拉並顯示 BTC/USDT 1h 蠟燭圖。
- `/api/data/symbols` 與 `/api/data/ohlcv?symbol=BTC/USDT&timeframe=1h` 在 Railway 返回數據（已 live，需確認非空）。

## 不在本批
- P3（backtest 歷史/匯出 CSV）、P4（首頁 dashboard/多用戶）。
- 後端 data API 不修改（已滿足需求）。
