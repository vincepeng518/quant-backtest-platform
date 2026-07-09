# 📈 加密貨幣回測實驗室 (Crypto Backtesting Lab)

一個用 Streamlit 打造的開源回測網站，支援加密貨幣資料（CCXT）與 CSV 上傳，提供完整的 Python 策略編寫環境與績效分析儀表板。

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-1.30+-FF4B4B.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## ✨ 功能特色

- 📊 **多元資料來源**
  - 透過 CCXT 自動抓取 100+ 加密貨幣交易所歷史 K 線
  - 支援上傳自有 CSV 資料
  - 支援 1m ~ 1w 多種時間框架

- 🧠 **完整 Python 策略編輯器**
  - 6 個預設策略範本（SMA、RSI、布林通道、MACD、網格、海龜）
  - 可在網站內直接編寫 Pine Script 風格的 Python 策略
  - 安全沙箱執行使用者代碼

- ⚙️ **完整回測引擎**
  - 支援多空雙向
  - 支援停損停利
  - 含手續費與滑點模擬

- 📈 **專業級績效分析**
  - 權益曲線 vs 買進持有
  - 回撤曲線
  - 月度報酬熱力圖
  - 完整交易明細（可下載 CSV）
  - Sharpe Ratio、最大回撤、利潤因子、勝率等

## 🚀 快速開始

### 本地端執行

```bash
# 1. 安裝依賴
pip install -r requirements.txt

# 2. 啟動應用
streamlit run app.py
```

瀏覽器會自動開啟 `http://localhost:8501`

### 部署到 Streamlit Cloud（免費）

1. 將此專案推送到 GitHub
2. 前往 [share.streamlit.io](https://share.streamlit.io)
3. 連結你的 GitHub repo
4. 設定 Main file: `app.py`
5. 點擊 Deploy

幾分鐘後你就會得到一個公開的 HTTPS 網址！

## 📁 專案結構

```
backtest_web/
├── app.py                    # Streamlit 主應用
├── requirements.txt          # Python 依賴
├── .streamlit/
│   └── config.toml           # 主題與伺服器設定
├── utils/
│   ├── backtester.py         # 回測引擎
│   └── data_fetcher.py       # 資料抓取
└── strategies/
    └── strategy_runner.py    # 策略執行器（含 6 個範本）
```

## 🧪 撰寫自訂策略

策略代碼需定義 `generate_signals(df, params)` 函數，回傳兩個 `pd.Series` (bool)：

```python
def generate_signals(df, params):
    # 範例：均線交叉
    fast = params.get("fast_period", 20)
    slow = params.get("slow_period", 50)

    df["sma_fast"] = df["close"].rolling(fast).mean()
    df["sma_slow"] = df["close"].rolling(slow).mean()

    entries = (df["sma_fast"] > df["sma_slow"]) & (df["sma_fast"].shift(1) <= df["sma_slow"].shift(1))
    exits = (df["sma_fast"] < df["sma_slow"]) & (df["sma_fast"].shift(1) >= df["sma_slow"].shift(1))

    return entries.fillna(False), exits.fillna(False)
```

### `df` 可用欄位
- `df['open']`, `df['high']`, `df['low']`, `df['close']`, `df['volume']` — OHLCV 資料
- `df.index` — 時間索引（DatetimeIndex）

### `params` 變數
從側邊欄的「策略參數」JSON 解析而來，可在代碼中用 `params['xxx']` 讀取。

## 📊 績效指標說明

| 指標 | 說明 | 健康值 |
|------|------|-------|
| **總報酬率** | 策略總回報 | > 0 |
| **最大回撤** | 歷史最大虧損幅度 | < 20% |
| **Sharpe Ratio** | 風險調整後報酬 | > 1.5 |
| **勝率** | 獲利交易佔比 | > 50% |
| **利潤因子** | 總獲利 / 總虧損 | > 1.5 |
| **平均獲利 / 虧損** | 風報比的依據 | 獲利 > 虧損 |

## 🔧 設定

`.streamlit/config.toml` 已預設深色主題配色，符合交易員工作環境。

## ⚠️ 免責聲明

本工具僅供研究與教育用途。回測結果不代表未來表現：
- 過度擬合（overfitting）是回測的最大陷阱
- 滑點與流動性在真實環境中差異極大
- 交易涉及重大風險，可能損失全部本金
- 過去的績效**不保證**未來收益

## 📜 授權

MIT License

## 🙏 致謝

- [CCXT](https://github.com/ccxt/ccxt) - 統一加密貨幣交易所 API
- [Streamlit](https://streamlit.io/) - 神奇的 Python 網頁框架
- [Plotly](https://plotly.com/) - 互動式圖表
