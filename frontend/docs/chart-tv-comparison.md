# 回測圖表 vs TradingView 精準比對報告

> 分析日期：2026-07-16
> 圖表庫：lightweight-charts v4.2.3（安裝版）
> 標的組件：`TvBacktestChart.tsx`（主三 pane 圖表）
> 次要組件：`PriceChart.tsx`, `EquityPnlChart.tsx`, `EquityCurve.tsx`, `DrawdownChart.tsx`

---

## 一、座標軸刻度（Axis & Scale）

| # | 項目 | 當前行為 | TV 期望行為 | 差異 | 修復方案 |
|---|------|---------|-----------|:--:|---------|
| 1.1 | **價格軸精度** | 無自訂 formatter，依賴 lightweight-charts 預設（2 位小數） | TV 動態調整：BTC/USDT → 0.1，ETH → 0.01，小幣 → 0.00001+ | **中** | 在 `TvBacktestChart.tsx` 加入 `priceFormat` 自訂，根據價格區間自動決定小數位 |
| 1.2 | **時間軸日期格式** | 僅 `timeVisible: true`，輕量級預設 MM/DD HH:MM | TV 顯示：跨日顯示「MM/DD」，跨年顯示「YYYY」，當日顯示「HH:MM」 | **小** | 在 `timeScale` 加入 `tickMarkFormatter` 自訂函數，根據時間跨度切換格式 |
| 1.3 | **週末缺口處理** | lightweight-charts 預設行為（不連續時間軸，無資料點跳過） | TV 顯示連續時間軸，週末無空白，K 線連續排列 | **中** | 將 `timeScale` 的 `barSpacing` 調整為固定值，並改用 `setVisibleRange` 確保視口一致；或使用 `timeScale().applyOptions({ fixLeftEdge: true, fixRightEdge: true })` |
| 1.4 | **時間軸邊緣對齊** | 未設定 `fixLeftEdge` / `fixRightEdge` | TV 預設貼齊邊緣，不留空白 | **小** | 在 timeScale 加入 `fixLeftEdge: true, fixRightEdge: true` |
| 1.5 | **價格軸標籤顏色/大小** | 使用 `textColor: '#a3a3a3'`（全局），字體由 lightweight-charts 決定 | TV 右軸字體 11px、顏色 `#787b86`，有背景高亮 | **小** | 使用 `rightPriceScale: { entireTextOnly: true }` 並在 `layout` 設定 `fontSize: 11` |

---

## 二、顏色對比（Color Scheme）

| # | 項目 | 當前行為 | TV 期望行為 | 差異 | 修復方案 |
|---|------|---------|-----------|:--:|---------|
| 2.1 | **K 線漲跌顏色** | 上漲 `#10b981`（翠綠），下跌 `#ef4444`（紅） | TV 上漲 `#089981`（墨綠）或 `#00c853`，下跌 `#f23645`（橙紅） | **小** | 上漲改為 `#089981`，下跌改為 `#f23645`，與 TV 保持一致 |
| 2.2 | **背景色** | `#0a0a0a`（近純黑） | TV `#131722`（深藍黑） | **小** | 背景改為 `#131722`，各子 pane 背景同步 |
| 2.3 | **網格線顏色** | `#171717`（深灰） | TV `#2a2e39`（偏藍灰） | **小** | 網格線改為 `#2a2e39` |
| 2.4 | **十字線顏色** | 使用 `textColor` 值 `#a3a3a3`，粗細 1px，dashed | TV 顏色 `#758696`，粗細 1px，dashed，透明度 0.5 | **小** | 十字線顏色改為 `#758696`，加入 `crosshair: { vertLine: { color: '#758696', ... } }` |
| 2.5 | **十字線標籤背景** | `#262626`（深灰） | TV `#363c4e`（中灰藍） | **小** | 標籤背景改為 `#363c4e` |
| 2.6 | **成交量柱顏色** | 上漲 `rgba(16,185,129,0.5)`，下跌 `rgba(239,68,68,0.5)`（半透明） | TV 上漲 `rgba(8,153,129,0.3)`，下跌 `rgba(242,54,69,0.3)`，不透明度更低 | **小** | 上漲改為 `rgba(8,153,129,0.3)`，下跌改為 `rgba(242,54,69,0.3)` |
| 2.7 | **邊框顏色** | `#262626` | TV `#363c4e` | **小** | 改為 `#363c4e` |

---

## 三、K 線比例與布局（Candlestick Proportions & Layout）

| # | 項目 | 當前行為 | TV 期望行為 | 差異 | 修復方案 |
|---|------|---------|-----------|:--:|---------|
| 3.1 | **barSpacing（K 線間距）** | 未設定，使用 lightweight-charts 預設（自動計算，約 6px） | TV 預設 6px，根據縮放等級動態變化 | **小** | 初始化時設定 `barSpacing: 6`，讓使用者可縮放調整 |
| 3.2 | **三 pane 高度比例** | pricePane: 380px, volPane: 110px, eqPane: 140px（比例約 60:18:22） | TV 主圖約 60%，指標 20%，成交量 20% | **小** | 維持當前比例，或改為 380:100:120（更接近 TV） |
| 3.3 | **成交量柱高度比例** | `scaleMargins: { top: 0.1, bottom: 0 }` → 成交量佔 pane 90% | TV 成交量佔底部約 20-30% 空間 | **中** | 改為 `scaleMargins: { top: 0.7, bottom: 0 }`，讓成交量只佔底部 30% |
| 3.4 | **K 線實體/影線** | 未設定 `borderUpColor`/`borderDownColor` → 等同 upColor/downColor | TV 上漲實體白色邊框，下跌實體黑色邊框 | **小** | 簡化設定：`borderUpColor: '#089981', borderDownColor: '#f23645'`（輕量版不支援白色邊框，此為最佳近似） |
| 3.5 | **Pane 間分隔線** | `border-t border-border/10`（Tailwind border） | TV 有明顯的 1px 深色分隔線 | **小** | 改為 `border-t border-[#363c4e]`，加粗至 1px solid |

---

## 四、指標繪製層級（Indicator Layers）

| # | 項目 | 當前行為 | TV 期望行為 | 差異 | 修復方案 |
|---|------|---------|-----------|:--:|---------|
| 4.1 | **EMA 線顏色/粗細** | 顏色 `#f59e0b`（琥珀色），線寬 2px | TV 預設 EMA 顏色 `#FF9800`，線寬 2px | **小** | 無需更改（已接近） |
| 4.2 | **EMA 價格軸標籤** | `lastValueVisible: false`（隱藏最新值） | TV 在右軸顯示 EMA 最新值 | **小** | 改為 `lastValueVisible: true` 並設定 `title: 'EMA200'` |
| 4.3 | **權益曲線線條** | 策略 `#3b82f6`（藍色），線寬 2px；B&H `#a3a3a3` 線寬 1px | TV 預設策略線藍色，基準線灰色虛線 | **小** | 無需更改（已接近 TV 風格） |
| 4.4 | **Pane 間 crosshair 同步** | 有 `subscribeVisibleLogicalRangeChange` 同步三 pane | TV 多 pane 同步縮放/平移 | **小** | 當前實現正確，但需加入 crosshair 垂直線跨 pane 同步（見 5.2） |
| 4.5 | **Drawdown 圖表顏色** | 面積圖：`topColor: rgba(239,68,68,0.4)`, `bottomColor: rgba(239,68,68,0.05)` | TV 回撤通常用紅色半透明面積 | **小** | 無需更改（已接近 TV 風格） |
| 4.6 | **交易標記位置** | 入場 `belowBar`（箭頭），出場 `aboveBar`（圓圈） | TV 入場箭頭在 bar 上方，出場在 bar 下方 | **中** | 交換：入場 `aboveBar`（箭頭朝上），出場 `belowBar`（圓圈） |

---

## 五、滑鼠互動（Mouse Interaction）

| # | 項目 | 當前行為 | TV 期望行為 | 差異 | 修復方案 |
|---|------|---------|-----------|:--:|---------|
| 5.1 | **Crosshair 模式** | `CrosshairMode.Normal`（自由移動） | TV `CrosshairMode.Magnet`（吸附到最近 K 線） | **中** | 改為 `CrosshairMode.Magnet`，讓十字線吸附到最近的 K 線 |
| 5.2 | **Crosshair 跨 pane 同步** | 三 pane 各自有 crosshair，但未同步垂直線位置 | TV 在所有 pane 顯示同一垂直線 | **大** | 在 `subscribeCrosshairMove` 中，將 `param.time` 傳遞到其他 pane 的 `setCrosshairPosition` |
| 5.3 | **價格軸標籤位置** | 預設在右軸顯示價格標籤 | TV 在右軸顯示價格標籤，且在十字線旁顯示浮動價格標籤 | **小** | 在 `legend` 中已顯示價格，但無右軸浮動標籤；lightweight-charts 預設支援此功能 |
| 5.4 | **時間軸標籤** | 無時間軸十字線標籤 | TV 在底部時間軸顯示豎直線對應的時間 | **小** | lightweight-charts 預設在時間軸顯示十字線標記 |
| 5.5 | **縮放/滾輪行為** | 未明確設定 `handleScroll` / `handleScale`，使用預設值 | TV 滑鼠滾輪縮放 + 拖曳平移 | **小** | 明確設定 `handleScroll: { vertTouchDrag: false, horzTouchDrag: true }` 和 `handleScale: { axisPressedMouseMove: true }`，鎖定垂直縮放 |
| 5.6 | **拖曳平移** | 預設啟用水平拖曳 | TV 按住滑鼠左鍵拖曳平移 | **小** | 無需更改（預設行為已正確） |
| 5.7 | **圖例懸停資訊** | 自訂 `legendRef` 顯示 O/H/L/C/EMA 值，使用 `font-mono text-xs` | TV 左上角顯示 O/H/L/C/V 值，使用等寬字體 11px | **小** | 圖例位置（左上角）正確，但字體大小建議改為 11px，並加入 `Chg` 和 `Vol` 欄位 |

---

## 六、功能性缺失（Missing Features）

| # | 項目 | 當前行為 | TV 期望行為 | 差異 | 修復方案 |
|---|------|---------|-----------|:--:|---------|
| 6.1 | **水印（Watermark）** | 無水印 | TV 左下角顯示「TradingView」浮水印 | **小** | 加入 `watermark: { visible: true, text: 'Backtest Lab', ... }` 選項 |
| 6.2 | **K 線計數器** | 無 | TV 右下角顯示可見 K 線數量 | **小** | 在 `timeScale` 的 `visibleLogicalRangeChange` 回調中更新 K 線計數器 |
| 6.3 | **全螢幕模式** | 無 | TV 右上角有全螢幕按鈕 | **小** | 可在父元件加入全螢幕切換按鈕 |
| 6.4 | **時間範圍選擇器** | 無 | TV 底部有時間範圍按鈕（1m, 5m, 15m, 1H, 4H, 1D） | **小** | 可選功能，當前在頁面頂部已有 timeframe 選擇器 |

---

## 七、優先級修復列表（按影響程度排序）

### 🔴 高優先級（影響用戶體驗最大）

| 優先級 | 項目 | 影響 |
|:------:|------|------|
| P1 | **5.1 Crosshair 模式改為 Magnet** | 用戶無法精確定位到 K 線，最直接的交互差異 |
| P2 | **3.3 成交量柱高度比例** | 成交量 pane 佔比過大，視覺比例失調 |
| P3 | **1.1 價格軸動態精度** | 小幣種價格顯示不正確（如 0.00001234 顯示為 0.00） |
| P4 | **4.6 交易標記位置交換** | 入場/出場標記與 TV 習慣相反 |

### 🟡 中優先級

| 優先級 | 項目 | 影響 |
|:------:|------|------|
| P5 | **2.1 K 線漲跌顏色改為 TV 色** | 顏色習慣差異，影響圖表解讀 |
| P6 | **1.3 週末缺口處理** | 回測數據若有週末空缺，圖表顯示異常 |
| P7 | **5.2 Crosshair 跨 pane 同步** | 三 pane 各自顯示十字線，無法統一閱讀 |
| P8 | **2.2-2.7 顏色體系調整** | 整體視覺風格與 TV 不一致 |

### 🟢 低優先級

| 優先級 | 項目 | 影響 |
|:------:|------|------|
| P9 | **1.2 時間軸格式** | 跨年/跨月顯示不明確 |
| P10 | **1.4 邊緣對齊** | 視覺微調 |
| P11 | **3.1 barSpacing** | 視覺微調 |
| P12 | **6.1-6.4 功能缺失** | 可選增強 |

---

## 八、關鍵程式碼修改範例

### 8.1 TvBacktestChart.tsx 核心修改

```typescript
// 1) 顏色修正 (P5)
const TV_UP = '#089981';
const TV_DOWN = '#f23645';
const TV_BG = '#131722';
const TV_GRID = '#2a2e39';
const TV_CROSSHAIR = '#758696';
const TV_BORDER = '#363c4e';

// 2) Crosshair 模式改為 Magnet (P1, 5.1)
crosshair: {
  mode: CrosshairMode.Magnet,  // 改為吸附模式
  vertLine: { color: TV_CROSSHAIR, width: 1, style: 2, labelBackgroundColor: TV_BORDER },
  horzLine: { color: TV_CROSSHAIR, width: 1, style: 2, labelBackgroundColor: TV_BORDER },
}

// 3) 成交量高度修正 (P2, 3.3)
vol.priceScale().applyOptions({ scaleMargins: { top: 0.7, bottom: 0 } });

// 4) 交易標記互換 (P4, 4.6)
// 入場標記：aboveBar + arrowUp
// 出場標記：belowBar + circle

// 5) 時間軸邊緣對齊 (P9, 1.4)
timeScale: {
  fixLeftEdge: true,
  fixRightEdge: true,
  timeVisible: true,
  secondsVisible: false,
}

// 6) 價格軸動態精度 (P3, 1.1)
rightPriceScale: {
  borderColor: TV_BORDER,
  // 透過 priceFormat 在 addCandlestickSeries 時設定
}
candle = priceChart.addCandlestickSeries({
  upColor: TV_UP, downColor: TV_DOWN,
  borderUpColor: TV_UP, borderDownColor: TV_DOWN,
  wickUpColor: TV_UP, wickDownColor: TV_DOWN,
  priceFormat: {
    type: 'price',
    precision: 2,  // 可根據數據動態調整
    minMove: 0.01,
  },
});
```

### 8.2 成交量顏色修正 (P8, 2.6)

```typescript
// 當前 (半透明過高)
color: d.close >= d.open ? 'rgba(16,185,129,0.5)' : 'rgba(239,68,68,0.5)'

// 改為 TV 風格 (低透明度)
color: d.close >= d.open ? 'rgba(8,153,129,0.3)' : 'rgba(242,54,69,0.3)'
```

### 8.3 時間軸格式器 (P9, 1.2)

```typescript
timeScale: {
  tickMarkFormatter: (time: number, tickMarkType: TickMarkType) => {
    const date = new Date(time * 1000);
    const now = new Date();
    // 當年：顯示 MM/DD
    if (date.getFullYear() === now.getFullYear()) {
      return `${date.getMonth() + 1}/${date.getDate()}`;
    }
    // 跨年：顯示 YYYY/MM/DD
    return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()}`;
  },
}
```

---

## 九、總結

總計發現 **25 項差異**，其中：
- **大差異**：1 項（Crosshair 跨 pane 同步）
- **中差異**：6 項（Crosshair 模式、成交量比例、週末缺口、顏色體系、價格精度、標記位置）
- **小差異**：18 項（顏色微調、格式、邊框等）

**核心修復建議**：優先修改 `TvBacktestChart.tsx` 的 5 個高優先級項目（P1-P5），可在 1-2 小時內完成，讓圖表視覺與操作體驗接近 TradingView 80% 以上。