# 回測績效視覺化面板 — 詳細前端規格（TradingView/Pine 還原）

> 來源需求：用戶以「量化交易前端工程師」視角給出的主圖績效面板精確視覺規範。
> 日期：2026-07-15　狀態：SPEC（待執行，接在 T1/T2 之後的 T2b）

## 與前一份 spec 的關係
前一份（backtest-tradingview-spec.md）的後端字段（net_profit / largest_loss / largest_loss_pct / direction / exit_reason / holding_bars）**全部繼續需要**。
本份是**前端主圖面板的精細化重做**——取代前份裡簡化的 MetricsCard 與 EquityCurve 擺放，改為完整績效面板組件。

---

## 一、關鍵數據佈局（圖表正上方，4 區塊）

以一行 4 欄 KPI 區塊置於主圖上方：

| 區塊 | 顯示內容 | 計算/來源 | 著色 |
|---|---|---|---|
| **總損益** | 絕對金額 + 百分比，如 `+132.07 USDT` / `+1.32%` | `net_profit`($) + `total_return_pct`(%) | 正綠 / 負紅 |
| **最大回撤** | 絕對金額 + 百分比 | `max_drawdown`(%) → 金額 = `initial_capital * max_drawdown/100` | 紅 |
| **獲利交易** | 勝率% + 比例，如 `34.59% 448/1295` | `win_rate`(%) + `winning_trades`/`total_trades` | 中性 |
| **獲利因子** | 小數值，如 `1.42` | `profit_factor` | 中性 |

## 二、圖例與控制面板（圖表左上方）
- **累計損益**（預設開啟）— 對應主圖資金曲線，toggle 開關
- **買進並持有** — 含可隱藏/顯示的圖示按鈕（eye icon），toggle 主圖 B&H 灰線
- **交易波動幅度** — 文字標籤 / 切換選項
- **漲幅與回撤** — 文字標籤 / 切換選項（控制下方直方圖或漲/回撤疊加）

## 三、主圖表與視覺細節
- **圖表庫**：Lightweight Charts（已裝 `^4.1.3`），暗色主題 `#0a0a0a`
- **主曲線**：累計損益（資金曲線），資金為正時線條預設綠色 `#10b981`，為負轉紅 `#ef4444`（用 `lineStyle` / 分段或 `createPriceLine` 0 基準線）
- **底部直方圖**：在主圖底部區域疊加「單筆交易盈虧柱狀圖」
  - 獲利交易 → 向上綠色柱 `#10b981`
  - 虧損交易 → 向下紅色柱 `#ef4444`
  - 柱高 = `abs(t.pnl)` 縮放，密集垂直排列，X 對齊各 trade 的 exit_time
  - 實作：用 Lightweight Charts 的 `addHistogramSeries`（作為獨立 pane 或 overlay at bottom）
- **X 軸上方狀態條**：極細一條，用紅/綠色塊標記持倉狀態（持多=綠、持空=紅、空手=透明），按時間軸對齊
  - 資料來源：後端需提供持倉區間（或由 trades 的 entry/exit 推導持倉段）

## 四、預設 JSON 測試資料結構
```json
{
  "metrics": {
    "net_profit": 132.07,
    "total_return_pct": 1.32,
    "max_drawdown_pct": 4.18,
    "initial_capital": 10000,
    "win_rate": 34.59,
    "winning_trades": 448,
    "total_trades": 1295,
    "profit_factor": 1.42
  },
  "equity_curve": [
    { "time": 1717200000, "equity": 10012.5 },
    { "time": 1717203600, "equity": 10025.1 }
  ],
  "buy_hold_equity": [
    { "time": 1717200000, "equity": 10005.0 }
  ],
  "trades": [
    {
      "entry_time": 1717200000, "exit_time": 1717236000,
      "direction": "long", "entry_price": 65000.0, "exit_price": 65120.0,
      "size": 0.002, "pnl": 24.0, "pnl_pct": 0.0018,
      "exit_reason": "signal", "holding_bars": 10
    }
  ],
  "position_status": [
    { "time": 1717200000, "state": "long" },
    { "time": 1717236000, "state": "flat" }
  ]
}
```

## 五、組件規劃（前端）
- 新建 `components/backtest/PerformancePanel.tsx` — 包裝 4 KPI 區塊 + 圖例控制 + 主圖
- 新建 `components/charts/EquityPnlChart.tsx` — 在 Lightweight Charts 中同時畫 equity line（綠/紅）+ 底部 histogram（單筆盈虧）+ 0 基準線
- 狀態條用輕量 DOM 疊加層（不進圖表引擎），對齊 X 軸時間
- `backtest/page.tsx` 結果區改為渲染 `<PerformancePanel .../>`，取代既有分散的 MetricsCard+EquityCurve+DrawdownChart 擺放

## 六、驗收
- [ ] 4 KPI 區塊顯示（總損益含$/%、最大回撤含$/%、獲利交易含%與比例、獲利因子）
- [ ] 圖例 4 項可切換，B&H 可隱藏
- [ ] 主圖綠/紅資金曲線 + 底部單筆盈虧直方圖
- [ ] X 軸上方紅綠狀態條
- [ ] 用預設 JSON 在本地/線上渲染無錯
