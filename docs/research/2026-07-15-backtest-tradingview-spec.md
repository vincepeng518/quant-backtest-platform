# 回測報表 — 開發規格（TradingView 還原 + Pine Script v6 對齊）

> 來源需求：用戶要求回測頁面視覺與 TradingView 一致，統計維度對齊 Pine Script v6 策略測試器。
> 日期：2026-07-15　狀態：SPEC（待執行）

## 現狀（已具備，勿重造）
- 前端依賴 `lightweight-charts@^4.1.3` ✅
- `components/charts/PriceChart.tsx`：K線 + `setMarkers` 接口 + OHLC 懸停圖例（crosshair）✅
- `components/charts/EquityCurve.tsx`：資金曲線（Strategy + Buy&Hold）✅
- `backtest/page.tsx` 已 import 並渲染 `PriceChart`（裸K線，未傳 markers）+ `EquityCurve` + `DrawdownChart` + `MetricsCard`×5 + `Trade Blotter` 表 ✅
- 後端 `profit_factor = 總毛利 / 總毛損` 定義正確 ✅
- 前端 `TradeRecord` 類型已定義 direction/size/pnl/pnl_pct 等 ✅

## 缺口（本規格要補的）
1. 主圖缺買賣標籤（markers 未接）
2. metrics 缺「淨利(絕對$)」「單筆最大虧損(金額+%)」
3. trades 缺 `direction`、`exit_reason`、`holding_bars`
4. Trade Blotter 不支援排序

---

## 一、前端視覺佈局（TradingView 風格）

將 `backtest/page.tsx` 結果區重組為**上下兩段**結構：

### 上段：主圖（帶買賣標籤的 K 線）
- 使用既有 `PriceChart`，傳入 `data`（OHLCV）+ `markers`（進出場點）
- `markers` 生成規則（在 store / 頁面層 mapping）：
  - 每筆 trade 的 `entry_time` → marker：`position: belowBar`、`shape: arrowUp`（多）/ `arrowDown`（空）、`color: #10b981 / #ef4444`、`text: 多/空+槓桿`
  - 每筆 trade 的 `exit_time` → marker：`position: aboveBar`、`shape: circle`、`color: 盈=#10b981 / 虧=#ef4444`、`text: PnL%`
- 保留既有 OHLC 懸停圖例（crosshair magnet mode）
- 圖表高度 450px，dark 主題 `#0a0a0a`

### 下段：資金曲線（Equity Curve）
- 使用既有 `EquityCurve`：Strategy 藍線 + Buy&Hold 灰線
- 高度 300px，懸停顯示「權益 $值」

### 指標卡（Pine v6 對齊，置於圖表上方）
- Net Profit（淨利 $）、Total Trades（總交易次數）、Win Rate（勝率 %）、
  Profit Factor（獲利因子）、Max Trade Loss（最大交易虧損 $ + %）
- 沿用既有 `MetricsCard` 組件，擴充為 5–6 張

---

## 二、後端數據規範（Pine Script v6 對齊）

### 2.1 指標計算定義（精確公式）
| 指標 | 定義 | 來源欄位 |
|---|---|---|
| 淨利 Net Profit | `final_equity - initial_capital`（絕對$） | `total_pnl` 已有，需在前端以 $ 顯示 |
| 總交易次數 | `len(trades)` | `total_trades` |
| 勝率 | `winners / total_trades * 100` | `win_rate` 已有 |
| 獲利因子 | `sum(pnl for winners) / abs(sum(pnl for losers))` | `profit_factor` 已有（定義正確）|
| **最大交易虧損（金額）** | `min(t.pnl for t in trades)`（最負單筆）| **新增** `largest_loss` |
| **最大交易虧損（%）** | `min(t.pnl_pct for t in trades) * 100` | **新增** `largest_loss_pct` |

### 2.2 需新增的後端字段
**`engine/backtester.py` `_calculate_metrics`**：
```python
losses = [t.pnl for t in losers]
largest_loss = min(losses) if losses else 0.0
largest_loss_pct = min([t.pnl_pct for t in losers if t.pnl_pct is not None], default=0.0)
```
加入 `BacktestResult` 欄位：`largest_loss: float = 0.0`、`largest_loss_pct: float = 0.0`

**`app/services/backtest_service.py` `get_results` metrics** 加入：
```python
"net_profit": float(r.total_pnl),
"largest_loss": r.largest_loss,
"largest_loss_pct": r.largest_loss_pct,
```

**`app/models/schemas.py` `MetricsOut`** 加入：
```python
net_profit: float = 0.0
largest_loss: float = 0.0
largest_loss_pct: float = 0.0
```

### 2.3 Trade 記錄擴充（明細表對齊）
**`engine/backtester.py` `Trade` dataclass** 新增：
```python
direction: str = "long"   # long / short，由 position.size 符號推導
exit_reason: str = ""     # "signal" / "stop" / "liquidation" / "end"
holding_bars: int = 0     # exit_idx - entry_idx
```
**`_calculate_metrics` 前**在 trade 生成處補 `direction`（size>0→long）、`holding_bars`（bar 差）。

**`TradeRecord` schema**（`app/models/schemas.py`）擴充：
```python
direction: str = "long"
exit_reason: str = ""
holding_bars: int = 0
```
**`backtest_service.get_results` trades mapping** 加入對應欄位。

---

## 三、交易列表（Trade Blotter）規格
- 欄位：# / Entry Time / Exit Time / Side(多/空) / Entry / Exit / Size(合約數) / PnL($) / PnL% / Exit Reason / Bars
- **排序功能**：點擊表頭排序，支援
  - 時間（Entry Time asc/desc）
  - 獲利（PnL asc/desc）
  - 用 `useState` + `useMemo` 在前端實作，不依賴額外表格套件（輕量、無新增依賴）
- 盈虧著色：綠/紅（沿用既有 `text-success` / `text-danger`）

---

## 四、驗收標準（Definition of Done）
- [ ] 主圖 K 線帶買賣進出場 markers（多空箭頭 + 盈虧圓點）
- [ ] 指標卡顯示淨利($) + 最大交易虧損(金額+%)
- [ ] 後端 `/api/backtest/results/{id}` 回傳 `net_profit` / `largest_loss` / `largest_loss_pct` 且值正確
- [ ] Trade 明細含 direction / exit_reason / holding_bars
- [ ] Trade Blotter 可點表頭按時間與獲利排序
- [ ] 線上實測：跑 `ma_cross` 回測 → 主圖出標籤、指標卡 5–6 項、表可排序
- [ ] `tsc` 0 錯、build 通、pytest 後端通

## 五、執行順序（建議）
1. 後端：`backtester.py`（Trade 欄位 + largest_loss 計算）→ `schemas.py` → `backtest_service.py`
2. 後端單測：構造 trades 驗證 largest_loss / net_profit
3. 前端：`MetricsCard` 擴充 + markers mapping + Trade Blotter 排序
4. 部署 Railway + Vercel，實測
