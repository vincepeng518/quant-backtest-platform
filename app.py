"""
Streamlit 回測網站主應用
支援：加密貨幣資料 (CCXT)、CSV 上傳、Python 策略代碼編寫、完整績效分析
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.subplots as sp
from plotly.subplots import make_subplots
from datetime import datetime, timezone

from utils.data_fetcher import (
    fetch_crypto_data, load_csv_data,
    get_available_exchanges, get_timeframes
)
from utils.backtester import BacktestEngine
from strategies.strategy_runner import (
    execute_user_strategy, get_template, list_templates
)


# === 頁面設定 ===
st.set_page_config(
    page_title="加密貨幣回測實驗室",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# === 自訂 CSS ===
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #00C9FF 0%, #92FE9D 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    .sub-header {
        color: #888;
        font-size: 1rem;
        margin-top: -10px;
        margin-bottom: 30px;
    }
    .metric-card {
        background-color: #1E1E1E;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #00C9FF;
    }
    .stCodeBlock { font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)


# === 標題 ===
st.markdown('<p class="main-header">📈 加密貨幣回測實驗室</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Crypto Backtesting Lab · Powered by CCXT + Streamlit</p>', unsafe_allow_html=True)


# === 側邊欄：資料來源 ===
with st.sidebar:
    st.header("📊 資料來源")

    data_source = st.radio(
        "選擇資料來源",
        ["加密貨幣 (CCXT)", "上傳 CSV"],
        index=0,
    )

    df = None
    data_info = ""

    if data_source == "加密貨幣 (CCXT)":
        col1, col2 = st.columns(2)
        with col1:
            exchange = st.selectbox("交易所", get_available_exchanges(), index=0)
        with col2:
            symbol = st.text_input("交易對", value="BTC/USDT")

        col3, col4 = st.columns(2)
        with col3:
            timeframe = st.selectbox("時間框架", get_timeframes(), index=4)
        with col4:
            days = st.number_input("回看天數", min_value=7, max_value=1825, value=180)

        if st.button("🔄 抓取資料", type="primary", use_container_width=True):
            with st.spinner(f"正在從 {exchange} 抓取 {symbol} 資料..."):
                try:
                    df = fetch_crypto_data(symbol, timeframe, days, exchange)
                    if df is not None and not df.empty:
                        st.session_state["df"] = df
                        st.success(f"✅ 抓取 {len(df):,} 根 K 線")
                    else:
                        st.error("❌ 抓取失敗：無資料")
                except Exception as e:
                    st.error(f"❌ 錯誤: {e}")

    else:  # CSV 上傳
        uploaded = st.file_uploader("上傳 CSV 檔案", type=["csv"])
        if uploaded is not None:
            try:
                df = load_csv_data(uploaded)
                if df is not None and not df.empty:
                    st.session_state["df"] = df
                    st.success(f"✅ 載入 {len(df):,} 筆資料")
            except Exception as e:
                st.error(f"❌ {e}")

    # 顯示已快取的資料
    if "df" in st.session_state and df is None:
        df = st.session_state["df"]
        st.info(f"📦 已載入快取資料：{len(df):,} 根 K 線")
        if st.button("🗑️ 清除資料", use_container_width=True):
            del st.session_state["df"]
            st.rerun()

    if df is not None and not df.empty:
        data_info = f"{len(df):,} 根 K 線 | {df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d')}"
        st.caption(data_info)

    st.divider()

    # === 回測設定 ===
    st.header("⚙️ 回測參數")
    initial_capital = st.number_input("初始資金 (USDT)", min_value=100.0, value=10000.0, step=1000.0)
    commission_pct = st.number_input("手續費 (%)", min_value=0.0, max_value=5.0, value=0.1, step=0.05) / 100
    slippage_pct = st.number_input("滑點 (%)", min_value=0.0, max_value=2.0, value=0.05, step=0.01) / 100

    direction = st.selectbox("交易方向", ["long (做多)", "short (做空)"], index=0)
    direction_code = "long" if direction.startswith("long") else "short"

    use_sl_tp = st.checkbox("啟用停損/停利")
    stop_loss = None
    take_profit = None
    if use_sl_tp:
        col5, col6 = st.columns(2)
        with col5:
            stop_loss = st.number_input("停損 (%)", min_value=0.1, max_value=50.0, value=2.0, step=0.5) / 100
        with col6:
            take_profit = st.number_input("停利 (%)", min_value=0.1, max_value=100.0, value=4.0, step=0.5) / 100


# === 主區域 ===
if df is None or df.empty:
    st.info("👈 請從左側選擇資料來源並載入資料")
    st.markdown("""
    ### 🚀 快速開始

    1. **選擇資料來源**（左側）
       - 加密貨幣：自動從 Binance、OKX、Bybit 等交易所抓取
       - CSV：上傳自己的 OHLCV 資料
    2. **選擇或撰寫策略**（下方）
       - 6 個預設策略範本
       - 支援完整 Python 代碼
    3. **執行回測**並查看績效指標與圖表

    ### 💡 提示
    - 策略代碼需定義 `generate_signals(df, params)` 函數
    - 回傳兩個 `pd.Series` (bool): (進場訊號, 出場訊號)
    - 可使用 `pd`, `np`, `params` 等變數
    """)
    st.stop()

# === 策略區 ===
st.header("🧠 策略程式碼")

# 策略範本選擇
col_t1, col_t2 = st.columns([3, 1])
with col_t1:
    template_choice = st.selectbox(
        "載入範本（可選）",
        ["（自訂）"] + list_templates(),
        index=1,
    )
with col_t2:
    st.write("")
    st.write("")
    if template_choice != "（自訂）" and st.button("📥 載入此範本"):
        st.session_state["strategy_code"] = get_template(template_choice)

# 策略代碼編輯器
if "strategy_code" not in st.session_state:
    st.session_state["strategy_code"] = get_template(list_templates()[0])

strategy_code = st.text_area(
    "Python 策略代碼（可編輯）",
    value=st.session_state["strategy_code"],
    height=320,
    help="定義函數：def generate_signals(df, params) -> (entries, exits)",
)

# 策略參數
with st.expander("🎛️ 策略參數（可在程式碼中用 params['xxx'] 讀取）", expanded=False):
    st.caption("輸入 JSON 格式，例如：{\"fast_period\": 20, \"slow_period\": 50}")
    params_text = st.text_area("參數", value='{"fast_period": 20, "slow_period": 50}', height=80)
    try:
        import json
        strategy_params = json.loads(params_text)
    except json.JSONDecodeError as e:
        st.error(f"❌ JSON 格式錯誤: {e}")
        strategy_params = {}


# === 執行回測 ===
st.divider()
col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 4])
with col_btn1:
    run_btn = st.button("▶️ 執行回測", type="primary", use_container_width=True)
with col_btn2:
    if st.button("💾 儲存策略代碼", use_container_width=True):
        st.session_state["strategy_code"] = strategy_code
        st.success("已儲存")

if not run_btn:
    st.stop()


# === 執行策略 ===
entries, exits, err = execute_user_strategy(strategy_code, df, strategy_params)

if err:
    st.error(err)
    st.stop()

if not entries.any():
    st.warning("⚠️ 策略沒有產生任何進場訊號。請檢查您的策略代碼或參數。")
    st.stop()


# === 跑回測 ===
with st.spinner("執行回測中..."):
    engine = BacktestEngine(
        df,
        initial_capital=initial_capital,
        commission=commission_pct,
        slippage=slippage_pct,
    )
    results = engine.run(
        entries=entries,
        exits=exits,
        direction=direction_code,
        stop_loss=stop_loss if use_sl_tp else None,
        take_profit=take_profit if use_sl_tp else None,
    )

result_df = results["data"]
trades = results["trades"]
metrics = results["metrics"]


# === 顯示績效指標 ===
st.header("📊 績效總覽")

if "error" in metrics:
    st.warning(metrics["error"])
    st.stop()

col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)

with col_m1:
    total_ret = metrics["total_return_pct"]
    st.metric("總報酬率", f"{total_ret:+.2f}%", delta=f"{total_ret - metrics['buy_hold_return_pct']:+.2f}% vs 買進持有")
with col_m2:
    st.metric("最終權益", f"${metrics['final_equity']:,.2f}")
with col_m3:
    st.metric("勝率", f"{metrics['win_rate']:.1f}%", delta=f"{metrics['n_trades']} 筆交易")
with col_m4:
    st.metric("最大回撤", f"{metrics['max_drawdown_pct']:.2f}%")
with col_m5:
    st.metric("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}")

col_m6, col_m7, col_m8, col_m9, col_m10 = st.columns(5)
with col_m6:
    st.metric("利潤因子", f"{metrics['profit_factor']:.2f}" if metrics['profit_factor'] != np.inf else "∞")
with col_m7:
    st.metric("買進持有報酬", f"{metrics['buy_hold_return_pct']:+.2f}%")
with col_m8:
    st.metric("平均獲利", f"{metrics['avg_win_pct']:+.2f}%")
with col_m9:
    st.metric("平均虧損", f"{metrics['avg_loss_pct']:+.2f}%")
with col_m10:
    st.metric("平均持倉 (h)", f"{metrics['avg_duration_hours']:.1f}")


# === 圖表 ===
st.header("📈 圖表分析")

tab1, tab2, tab3 = st.tabs(["權益曲線", "價格 + 進出場標記", "交易明細"])

with tab1:
    fig_equity = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3],
        subplot_titles=("權益曲線 vs 買進持有", "回撤")
    )

    fig_equity.add_trace(
        go.Scatter(x=result_df.index, y=result_df["equity"], name="策略權益",
                   line=dict(color="#00C9FF", width=2)),
        row=1, col=1
    )
    fig_equity.add_trace(
        go.Scatter(x=result_df.index, y=result_df["buy_hold"], name="買進持有",
                   line=dict(color="#FFA500", width=2, dash="dash")),
        row=1, col=1
    )

    # 回撤
    cummax = result_df["equity"].cummax()
    drawdown = (result_df["equity"] - cummax) / cummax * 100
    fig_equity.add_trace(
        go.Scatter(x=result_df.index, y=drawdown, name="回撤 (%)",
                   fill="tozeroy", line=dict(color="#FF4B4B", width=1)),
        row=2, col=1
    )

    fig_equity.update_layout(
        height=600,
        hovermode="x unified",
        template="plotly_dark",
        showlegend=True,
    )
    fig_equity.update_yaxes(title_text="權益 (USDT)", row=1, col=1)
    fig_equity.update_yaxes(title_text="回撤 (%)", row=2, col=1)
    st.plotly_chart(fig_equity, use_container_width=True)

with tab2:
    # 顯示最近 200 根 K 線（避免圖太擠）
    display_df = result_df.tail(200) if len(result_df) > 200 else result_df

    fig_price = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
        subplot_titles=("價格走勢 + 進出場訊號", "成交量")
    )

    fig_price.add_trace(
        go.Candlestick(
            x=display_df.index,
            open=display_df["open"],
            high=display_df["high"],
            low=display_df["low"],
            close=display_df["close"],
            name="K 線"
        ),
        row=1, col=1
    )

    # 進場點
    entries_in_view = display_df[display_df["entry"]]
    if not entries_in_view.empty:
        fig_price.add_trace(
            go.Scatter(
                x=entries_in_view.index,
                y=entries_in_view["close"],
                mode="markers",
                name="進場",
                marker=dict(symbol="triangle-up", size=12, color="#00FF7F",
                            line=dict(color="white", width=1))
            ),
            row=1, col=1
        )

    # 出場點
    exits_in_view = display_df[display_df["exit"]]
    if not exits_in_view.empty:
        fig_price.add_trace(
            go.Scatter(
                x=exits_in_view.index,
                y=exits_in_view["close"],
                mode="markers",
                name="出場",
                marker=dict(symbol="triangle-down", size=12, color="#FF4B4B",
                            line=dict(color="white", width=1))
            ),
            row=1, col=1
        )

    # 成交量
    colors = ["#FF4B4B" if display_df["close"].iloc[i] < display_df["open"].iloc[i] else "#00C9FF"
              for i in range(len(display_df))]
    fig_price.add_trace(
        go.Bar(x=display_df.index, y=display_df["volume"], name="成交量", marker_color=colors),
        row=2, col=1
    )

    fig_price.update_layout(
        height=700,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        showlegend=True,
    )
    st.plotly_chart(fig_price, use_container_width=True)

with tab3:
    if trades:
        trades_df = pd.DataFrame(trades)
        trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"]).dt.tz_localize(None)
        trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"]).dt.tz_localize(None)
        trades_df["duration_hours"] = trades_df["duration_hours"].round(2)
        trades_df["pnl_pct"] = (trades_df["pnl_pct"] * 100).round(2)
        trades_df["pnl"] = trades_df["pnl"].round(2)
        trades_df["entry_price"] = trades_df["entry_price"].round(2)
        trades_df["exit_price"] = trades_df["exit_price"].round(2)

        st.dataframe(
            trades_df,
            use_container_width=True,
            column_config={
                "entry_time": st.column_config.DatetimeColumn("進場時間", format="YYYY-MM-DD HH:mm"),
                "exit_time": st.column_config.DatetimeColumn("出場時間", format="YYYY-MM-DD HH:mm"),
                "direction": "方向",
                "entry_price": st.column_config.NumberColumn("進場價", format="$%.2f"),
                "exit_price": st.column_config.NumberColumn("出場價", format="$%.2f"),
                "pnl_pct": st.column_config.NumberColumn("報酬率", format="%.2f%%"),
                "pnl": st.column_config.NumberColumn("損益 (USDT)", format="$%.2f"),
                "duration_hours": st.column_config.NumberColumn("持倉時數", format="%.1f h"),
                "exit_reason": "出場原因",
            },
            hide_index=True,
        )

        # 下載按鈕
        csv = trades_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 下載交易明細 CSV",
            data=csv,
            file_name=f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )
    else:
        st.info("無交易記錄")


# === 月度績效熱力圖 ===
st.header("🔥 月度績效")
if trades:
    trades_df = pd.DataFrame(trades)
    trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"]).dt.tz_localize(None)
    trades_df["year"] = trades_df["entry_time"].dt.year
    trades_df["month"] = trades_df["entry_time"].dt.month
    monthly = trades_df.groupby(["year", "month"])["pnl_pct"].sum() * 100
    monthly_pivot = monthly.unstack(fill_value=0)

    if not monthly_pivot.empty:
        fig_heatmap = go.Figure(data=go.Heatmap(
            z=monthly_pivot.values,
            x=[f"{m}月" for m in monthly_pivot.columns],
            y=monthly_pivot.index,
            colorscale="RdYlGn",
            zmid=0,
            text=np.round(monthly_pivot.values, 2),
            texttemplate="%{text}%",
            textfont={"size": 12},
            colorbar=dict(title="月報酬 %"),
        ))
        fig_heatmap.update_layout(
            height=300,
            template="plotly_dark",
            title="月度報酬率熱力圖",
        )
        st.plotly_chart(fig_heatmap, use_container_width=True)


# === 頁尾 ===
st.divider()
st.caption("⚠️ 免責聲明：本工具僅供研究與教育用途。回測結果不代表未來表現。交易涉及風險，過去的績效不保證未來收益。")
