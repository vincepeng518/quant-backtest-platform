# 交易框架評估：vnpy vs KungFu

> 針對 vincepeng 的加密套利場景（BingX / Polymarket / Predict.fun）
> 現狀：arb-bot = Python sleep-loop 輪詢（1s），DRY_RUN 紙上，無套利空間（Poly 卡 0.99）

## 一、核心差異

| 維度 | **vnpy** (vnpy/vnpy) | **KungFu** (kungfu-systems/kungfu v3.0) |
|---|---|---|
| 定位 | 中低頻全功能平台 | 中高頻低延遲執行引擎 |
| 語言 | Python（事件驅動） | C++20 核心 + Python/C++ 策略 |
| 延遲 | ms ~ μs | 微秒級，納秒時間戳 |
| 架構 | EventEngine(pub-sub) + MainEngine + Gateway | 長拳(數據) + 易筋經(時序DB) + 咏春(策略) |
| 櫃台 | 30+ gateway，**含 vnpy_binance**（加密） | XTP（中國股/期貨），加密需自寫 gateway |
| 回測 | 內建 Backtester（日/分鐘級） | 無內建（執行導向） |
| 風控 | risk_manager 模組 | 內建 |
| 數據 | SQLite/MySQL/QuestDB/TDengine/DolphinDB | 易筋經自研時序DB |
| 前端 | Qt GUI / WebTrader | Electron + Vue.js |
| 編譯 | pip install，無編譯 | cmake + Node + C++20，重 |
| 舊機 1GB RAM | ✅ 可跑（Python 輕） | ❌ 編譯/運行都吃力 |

## 二、對你的硬限制

1. **舊機 64.188.26.13 = 1GB RAM**
   - KungFu：C++20 編譯需 >2GB，運行後台也重 → **不可行**
   - vnpy：pip 安裝，Python 進程 ~200-400MB → **可行**

2. **加密櫃台**
   - vnpy：有 `vnpy_binance`（現貨/合約）。BingX/Poly/Predict 無現成 gateway，需自寫（但 vnpy gateway 介面清晰，照 binance 改即可）
   - KungFu：無加密 gateway，要從零寫 C++ gateway → 成本極高

3. **你的 arb 場景現狀**
   - 跨所 BTC 5m 套利：Poly 盤口卡 0.99/0.01，無空間（已驗證）
   - 單側 Predict YES+NO = 1.01 > 1，無空間
   - **結論**：現階段不是「框架不夠快」，是「市場沒套利空間」。換框架不會創造空間。

## 三、落地路徑

### 選 A：vnpy（中低頻，推薦）
1. 舊機 `pip install vnpy`（或 vnpy_binance）
2. 寫 `BingXGateway`（仿 BinanceGateway，改 REST/WS endpoint）
3. 把 arb-bot 邏輯搬進 `CtaTemplate`：
   - `on_tick()` 取代 sleep-loop
   - `send_order()` 取代手刻 POST
   - 內建風控（固定手續費/倉位上限）
4. 回測用 vnpy Backtester 驗證策略（你已有 Crypto-Backtesting-Lab，可併用）
- 優點：一站式、有回測、加密 gateway 可寫
- 缺點：延遲 ms 級（夠中低頻，不夠高頻）

### 選 B：KungFu（中高頻，不推薦）
1. 需 2GB+ 機器（舊機帶不動）→ 要升級或另租
2. 自寫 C++ crypto gateway（對接 BingX/Poly WebSocket）
3. 策略用 C++/Python 寫詠春引擎
- 優點：微秒級、專業執行
- 缺點：編譯重、無加密 gateway、舊機不可行、學習曲線陡

## 四、我的建議

**短期（現在）**：不換框架。
- arb-bot 已能跑（紙上），市場無空間，換框架無效。
- 把精力放「找有空間的標的/策略」，不是「換更快的引擎」。

**中期（若有中低頻策略要實盤）**：vnpy。
- 舊機能跑，有 binance gateway 可改 BingX，回測+實盤一條龍。
- 遷移成本：~1-2 天寫 gateway + 搬邏輯。

**長期（若要做市/高頻）**：KungFu + 升級機器。
- 但那是另一個量級的投入，現階段不急。

## 五、決策點

- 你要「中低頻實盤雛形」→ 我幫你搭 vnpy + BingX gateway（舊機）
- 你要「先研究別的策略」→ arb-bot 維持，找空間
- 你要「高頻夢」→ 先租 4GB+ 機 + KungFu 評估

---
*生成：2026-07-22 | 基於 github.com/vnpy/vnpy + kungfu-systems/kungfu@v3.0 研究*
