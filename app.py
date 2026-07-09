"""
Streamlit 回測網站主應用
支援：加密貨幣資料 (CCXT)、CSV 上傳、Python 策略代碼編寫、Walk-Forward 驗證、自動參數優化
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timezone
import json
import time

from utils.data_fetcher import (
    fetch_crypto_data, load_csv_data,
    get_available_exchanges, get_timeframes,
    get_exchange_display_name, get_default_symbol,
    get_bingx_popular_symbols,
)
from utils.backtester import BacktestEngine
from utils.pair_backtester import PairBacktestEngine
from utils.data_fetcher import fetch_pair_data, get_pair_templates
from utils.walk_forward import WalkForwardValidator
from utils.optimizer import ParameterOptimizer, calculate_overfit_score
from strategies.strategy_runner import (
    execute_user_strategy, get_template, list_templates,
    get_param_space, get_default_params
)
from utils.strategy_library import (
    validate_strategy_code, extract_strategy_name, extract_strategy_description,
    load_strategy_from_file, load_strategy_from_pasted_code,
    SAMPLE_STRATEGIES,
)
from utils.ui_components import (
    render_overview, render_performance_summary,
    render_list_of_trades, render_charts,
    TV_COLORS,
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
st.markdown('<p class="sub-header">Crypto Backtesting Lab · AI 自動參數優化 · Walk-Forward 驗證</p>', unsafe_allow_html=True)


# === 側邊欄：資料來源 ===
with st.sidebar:
    st.header("📊 資料來源")

    data_source = st.radio(
        "選擇資料來源",
        ["加密貨幣 (CCXT)", "上傳 CSV", "配對交易 (Pair)"],
        index=0,
    )

    # 是否配對交易
    is_pair_trading = (data_source == "配對交易 (Pair)")

    df = None
    data_info = ""

    if data_source == "加密貨幣 (CCXT)":
        # 交易所選擇（用顯示名稱）
        exchange_ids = get_available_exchanges()
        exchange_labels = {eid: get_exchange_display_name(eid) for eid in exchange_ids}
        # BingX 預設
        default_idx = exchange_ids.index("bingx") if "bingx" in exchange_ids else 0
        col1, col2 = st.columns(2)
        with col1:
            selected_exchange = st.selectbox(
                "交易所",
                exchange_ids,
                index=default_idx,
                format_func=lambda x: f"{exchange_labels.get(x, x)}  ({x})",
            )
        with col2:
            # 預設交易對
            default_sym = get_default_symbol(selected_exchange)
            symbol = st.text_input("交易對", value=default_sym, key="symbol_input")

        # BingX 熱門交易對快速選擇
        if selected_exchange == "bingx":
            popular = get_bingx_popular_symbols()
            with st.expander("⭐ BingX 熱門交易對", expanded=False):
                st.caption("點擊按鈕快速填入交易對")
                # 2 欄全寬按鈕，每個按鈕只顯示簡短名稱
                for i in range(0, len(popular), 2):
                    cols = st.columns(2)
                    for j, item in enumerate(popular[i:i+2]):
                        with cols[j]:
                            label = f"**{item['short']}**"
                            if st.button(label, key=f"sym_{item['full']}",
                                          use_container_width=True):
                                st.session_state["symbol_input"] = item["full"]
                                st.rerun()

        col3, col4 = st.columns(2)
        with col3:
            timeframe = st.selectbox("時間框架", get_timeframes(), index=4, key="timeframe_input")
        with col4:
            days = st.number_input("回看天數", min_value=7, max_value=1825, value=180, key="days_input")

        if st.button("🔄 抓取資料", type="primary", use_container_width=True):
            with st.spinner(f"正在從 {get_exchange_display_name(selected_exchange)} 抓取 {symbol} 資料..."):
                try:
                    df = fetch_crypto_data(symbol, timeframe, days, selected_exchange)
                    if df is not None and not df.empty:
                        st.session_state["df"] = df
                        st.session_state["exchange"] = selected_exchange
                        st.session_state["symbol"] = symbol
                        st.session_state["timeframe"] = timeframe
                        st.success(f"✅ 從 {get_exchange_display_name(selected_exchange)} 抓取 {len(df):,} 根 K 線")
                    else:
                        st.error("❌ 抓取失敗：無資料（請檢查交易對是否正確）")
                except ValueError as e:
                    st.error(f"❌ 參數錯誤: {e}")
                except ConnectionError as e:
                    st.error(f"❌ 連線問題: {e}")
                except RuntimeError as e:
                    st.error(f"❌ 交易所錯誤: {e}")
                except Exception as e:
                    st.error(f"❌ 未預期錯誤 ({type(e).__name__}): {e}")

    else:  # CSV 上傳 or 配對交易
        if data_source == "上傳 CSV":
            uploaded = st.file_uploader("上傳 CSV 檔案", type=["csv"])
            if uploaded is not None:
                try:
                    df = load_csv_data(uploaded)
                    if df is not None and not df.empty:
                        st.session_state["df"] = df
                        st.success(f"✅ 載入 {len(df):,} 筆資料")
                except Exception as e:
                    st.error(f"❌ {e}")

        elif data_source == "配對交易 (Pair)":
            st.caption("📊 配對交易：同時下兩個反向部位（例如買 BTC + 空 ETH）")

            # 配對組合選擇
            pair_templates = get_pair_templates()
            pair_labels = {p["name"]: p for p in pair_templates}
            selected_pair_name = st.selectbox(
                "選擇配對組合",
                list(pair_labels.keys()),
                index=0,
            )
            selected_pair = pair_labels[selected_pair_name]
            st.caption(f"📈 {selected_pair['symbol1']} vs {selected_pair['symbol2']}")

            # 交易所 + 時間框架
            pc1, pc2 = st.columns(2)
            with pc1:
                pair_exchange = st.selectbox("交易所", get_available_exchanges(), index=0,
                                              format_func=lambda x: f"{get_exchange_display_name(x)} ({x})",
                                              key="pair_exchange")
            with pc2:
                pair_timeframe = st.selectbox("時間框架", get_timeframes(), index=4, key="pair_timeframe")

            pair_days = st.number_input("回看天數", min_value=7, max_value=1825, value=30, key="pair_days")

            if st.button("🔄 抓取配對資料", type="primary", use_container_width=True):
                with st.spinner(f"正在抓取 {selected_pair['symbol1']} + {selected_pair['symbol2']} 配對資料..."):
                    try:
                        pair_df = fetch_pair_data(
                            selected_pair["symbol1"],
                            selected_pair["symbol2"],
                            pair_timeframe,
                            pair_days,
                            pair_exchange,
                        )
                        if pair_df is not None and not pair_df.empty:
                            st.session_state["df"] = pair_df
                            st.session_state["is_pair"] = True
                            st.session_state["pair_info"] = selected_pair
                            st.success(f"✅ 抓取 {len(pair_df):,} 根配對 K 線")
                        else:
                            st.error("❌ 抓取失敗")
                    except Exception as e:
                        st.error(f"❌ {e}")

    # 顯示已快取的資料
    if "df" in st.session_state and df is None:
        df = st.session_state["df"]
        is_pair = st.session_state.get("is_pair", False)
        if is_pair:
            pair_info = st.session_state.get("pair_info", {})
            st.info(f"📦 配對資料：{pair_info.get('symbol1', '?')} + {pair_info.get('symbol2', '?')} ({len(df):,} 根 K 線)")
        else:
            st.info(f"📦 已載入快取資料：{len(df):,} 根 K 線")
        if st.button("🗑️ 清除資料", use_container_width=True):
            del st.session_state["df"]
            st.session_state["is_pair"] = False
            st.session_state.pop("pair_info", None)
            st.rerun()

    if df is not None and not df.empty:
        data_info = f"{len(df):,} 根 K 線 | {df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d')}"
        st.caption(data_info)

    st.divider()

    # === 策略管理（共用：所有分頁都能用） ===
    st.header("📚 策略管理")

    if "user_strategies" not in st.session_state:
        st.session_state["user_strategies"] = {}  # {name: code}

    with st.expander("📤 上傳 / 貼上策略", expanded=False):
        st.caption("三種方式加入策略到「我的策略庫」")

        # 方式 1：上傳 .py 檔案
        st.markdown("**① 上傳 .py 檔案**")
        uploaded_files = st.file_uploader(
            "選擇 .py 檔（可多選）",
            type=["py"],
            accept_multiple_files=True,
            key="strategy_uploader",
        )
        if uploaded_files:
            for f in uploaded_files:
                # 檢查是否已載入
                if f.name in st.session_state["user_strategies"]:
                    continue
                success, result, fname = load_strategy_from_file(f)
                if success:
                    name = extract_strategy_name(result, fallback=fname)
                    st.session_state["user_strategies"][fname] = result
                    st.success(f"✅ 已載入: **{name}** ({fname})")
                else:
                    st.error(result)

        st.divider()

        # 方式 2：貼上代碼
        st.markdown("**② 貼上 Python 代碼**")
        pasted_code = st.text_area(
            "貼上策略代碼",
            height=120,
            key="pasted_strategy",
            placeholder="def generate_signals(df, params):\n    ...",
        )
        pasted_name = st.text_input("策略名稱", value="我的策略", key="pasted_name")
        if st.button("➕ 加入到策略庫", use_container_width=True):
            if not pasted_code.strip():
                st.error("請貼上代碼")
            else:
                success, result = load_strategy_from_pasted_code(pasted_code)
                if success:
                    final_name = pasted_name.strip() or extract_strategy_name(pasted_code)
                    st.session_state["user_strategies"][final_name] = result
                    st.success(f"✅ 已加入: **{final_name}**")
                    st.rerun()
                else:
                    st.error(result)

        st.divider()

        # 方式 3：載入社群範本
        st.markdown("**③ 一鍵載入社群策略範本**")
        st.caption("內建 4 個進階策略範本")
        sample_cols = st.columns(2)
        sample_names = list(SAMPLE_STRATEGIES.keys())
        for i, sname in enumerate(sample_names):
            with sample_cols[i % 2]:
                if sname not in st.session_state["user_strategies"]:
                    if st.button(f"➕ {sname}", key=f"add_sample_{i}",
                                  use_container_width=True):
                        st.session_state["user_strategies"][sname] = SAMPLE_STRATEGIES[sname]
                        st.success(f"✅ 已加入: {sname}")
                        st.rerun()
                else:
                    st.button(f"✓ {sname}", key=f"has_sample_{i}",
                              disabled=True, use_container_width=True)

    # 顯示策略庫
    if st.session_state["user_strategies"]:
        st.markdown("**📋 我的策略庫**")
        for sname in list(st.session_state["user_strategies"].keys()):
            col_s1, col_s2 = st.columns([4, 1])
            with col_s1:
                st.caption(f"📄 {sname}")
            with col_s2:
                if st.button("🗑️", key=f"del_{sname}", help=f"刪除 {sname}"):
                    del st.session_state["user_strategies"][sname]
                    st.rerun()

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
    else:
        stop_loss = None
        take_profit = None


# === 主區域 ===
if df is None or df.empty:
    st.info("👈 請從左側選擇資料來源並載入資料")
    st.markdown("""
    ### 🚀 快速開始

    1. **選擇資料來源**（左側）
       - 加密貨幣：自動從 Binance、OKX、Bybit 等交易所抓取
       - CSV：上傳自己的 OHLCV 資料
    2. **選擇功能分頁**（下方）
       - 🎯 單次回測：基本回測與圖表
       - 🤖 自動參數優化：網格/隨機搜尋找最佳參數
       - 📊 Walk-Forward 驗證：避免過擬合的進階驗證

    ### 💡 三種模式比較

    | 模式 | 用途 | 速度 |
    |------|------|------|
    | 🎯 單次回測 | 快速驗證一個想法 | 秒級 |
    | 🤖 自動優化 | 找出最佳參數組合 | 分鐘級 |
    | 📊 Walk-Forward | 確認參數是否過擬合 | 10分鐘級 |

    ### 🧠 內建 14 種策略範本
    SMA 交叉、RSI、布林通道、MACD、網格、海龜、KDJ、CCI、Donchian、TEMA、VWAP、OBV、一目均衡表、Parabolic SAR
    """)
    st.stop()


# === 三大功能分頁 ===
main_tab1, main_tab2, main_tab3 = st.tabs([
    "🎯 單次回測",
    "🤖 自動參數優化",
    "📊 Walk-Forward 驗證"
])


# ===========================
# 分頁 1：單次回測
# ===========================
with main_tab1:
    st.header("🧠 策略程式碼")

    # 整合的策略來源選擇
    col_src1, col_src2 = st.columns([3, 1])
    with col_src1:
        # 組合選項：內建範本 + 我的策略庫
        all_sources = ["（自訂）"] + list_templates()
        if st.session_state.get("user_strategies"):
            all_sources += ["── 📚 我的策略庫 ──"] + list(st.session_state["user_strategies"].keys())
        template_choice = st.selectbox(
            "選擇策略來源",
            all_sources,
            key="template_select",
        )
    with col_src2:
        st.write("")
        st.write("")
        # 判斷來源類型
        if template_choice.startswith("──"):
            st.button("📥 載入", key="load_template", disabled=True, use_container_width=True)
        elif template_choice != "（自訂）" and st.button("📥 載入", key="load_template", use_container_width=True):
            if template_choice in list_templates():
                st.session_state["strategy_code"] = get_template(template_choice)
                st.session_state["current_template"] = template_choice
            elif template_choice in st.session_state.get("user_strategies", {}):
                st.session_state["strategy_code"] = st.session_state["user_strategies"][template_choice]
                st.session_state["current_template"] = template_choice
            st.rerun()

    if "strategy_code" not in st.session_state:
        st.session_state["strategy_code"] = get_template(list_templates()[0])
        st.session_state["current_template"] = list_templates()[0]

    strategy_code = st.text_area(
        "Python 策略代碼（可編輯）",
        value=st.session_state["strategy_code"],
        height=320,
        key="strategy_code_editor",
        help="定義函數：def generate_signals(df, params) -> (entries, exits)",
    )

    with st.expander("🎛️ 策略參數（JSON 格式）", expanded=False):
        # 自動填入當前範本的預設參數
        current_t = st.session_state.get("current_template", "")
        if current_t and current_t != "（自訂）":
            default_params = get_default_params(current_t)
        else:
            default_params = {"period": 20}
        default_json = json.dumps(default_params, indent=2, ensure_ascii=False)

        params_text = st.text_area("參數", value=default_json, height=100, key="params_text")
        try:
            strategy_params = json.loads(params_text)
        except json.JSONDecodeError as e:
            st.error(f"❌ JSON 格式錯誤: {e}")
            strategy_params = {}

    st.divider()
    col_btn1, col_btn2 = st.columns([1, 5])
    with col_btn1:
        run_single = st.button("▶️ 執行回測", type="primary", use_container_width=True, key="run_single")
    with col_btn2:
        if st.button("💾 儲存策略代碼", use_container_width=False):
            st.session_state["strategy_code"] = strategy_code
            st.success("已儲存")

    if not run_single:
        st.stop()

    # 執行策略
    entries, exits, err = execute_user_strategy(strategy_code, df, strategy_params)

    if err:
        st.error(err)
        st.stop()

    if not entries.any():
        st.warning("⚠️ 策略沒有產生任何進場訊號")
        st.stop()

    # 判斷是否配對交易
    is_pair = st.session_state.get("is_pair", False)
    pair_info = st.session_state.get("pair_info", {})

    # 跑回測（根據是否配對交易選擇引擎）
    with st.spinner("執行回測中..."):
        if is_pair and pair_info:
            # 配對交易
            st.info(f"🔗 配對交易模式：{pair_info.get('symbol1')} + {pair_info.get('symbol2')}")
            pair_direction = "pair_long" if direction_code == "long" else "pair_short"
            engine = PairBacktestEngine(
                df,
                symbol1=pair_info.get("symbol1", "BTC/USDT"),
                symbol2=pair_info.get("symbol2", "ETH/USDT"),
                initial_capital=initial_capital,
                commission=commission_pct,
                slippage=slippage_pct,
            )
            results = engine.run(entries, exits, direction=pair_direction,
                                  stop_loss=stop_loss, take_profit=take_profit)
        else:
            # 單標的
            engine = BacktestEngine(
                df, initial_capital=initial_capital,
                commission=commission_pct, slippage=slippage_pct,
            )
            results = engine.run(entries, exits, direction=direction_code,
                                  stop_loss=stop_loss, take_profit=take_profit)

    result_df = results["data"]
    trades = results["trades"]
    metrics = results["metrics"]

    if "error" in metrics:
        st.warning(metrics["error"])
        st.stop()

    # === TradingView 風格：4 分頁結果顯示 ===
    result_tab1, result_tab2, result_tab3, result_tab4 = st.tabs([
        "📊 Overview",
        "📈 Performance Summary",
        "📋 List of Trades",
        "🕯️ Charts"
    ])

    with result_tab1:
        render_overview(metrics, result_df, initial_capital)

    with result_tab2:
        render_performance_summary(trades, metrics)

    with result_tab3:
        render_list_of_trades(trades)

    with result_tab4:
        render_charts(result_df, trades)


# ===========================
# 分頁 2：自動參數優化
# ===========================
with main_tab2:
    st.header("🤖 自動參數優化")
    st.caption("自動測試所有參數組合，找出最佳表現。像 TradingView AI 一樣的全自動優化。")

    col_o1, col_o2 = st.columns([3, 1])
    with col_o1:
        # 整合策略來源
        opt_sources = list_templates()
        if st.session_state.get("user_strategies"):
            opt_sources += ["── 📚 我的策略庫 ──"] + list(st.session_state["user_strategies"].keys())
        opt_template = st.selectbox("選擇策略", opt_sources, key="opt_template")
    with col_o2:
        st.write("")
        st.write("")
        if opt_template.startswith("──"):
            st.button("📥 載入策略", key="load_opt_template", disabled=True, use_container_width=True)
        elif st.button("📥 載入策略", key="load_opt_template", use_container_width=True):
            if opt_template in list_templates():
                st.session_state["opt_code"] = get_template(opt_template)
                st.session_state["opt_param_space"] = get_param_space(opt_template)
                st.session_state["opt_default_params"] = get_default_params(opt_template)
            elif opt_template in st.session_state.get("user_strategies", {}):
                # 自訂策略：只載入代碼，參數空間留空
                st.session_state["opt_code"] = st.session_state["user_strategies"][opt_template]
                st.session_state["opt_param_space"] = {}
                st.session_state["opt_default_params"] = {}
                st.info("自訂策略：請手動設定參數空間")
            st.session_state["opt_current"] = opt_template
            st.rerun()

    if "opt_code" not in st.session_state:
        st.session_state["opt_code"] = get_template(list_templates()[0])
        st.session_state["opt_current"] = list_templates()[0]
        st.session_state["opt_param_space"] = get_param_space(list_templates()[0])
        st.session_state["opt_default_params"] = get_default_params(list_templates()[0])

    opt_code = st.text_area("策略代碼（可編輯）", value=st.session_state["opt_code"],
                              height=250, key="opt_code_editor")

    col_op1, col_op2 = st.columns(2)
    with col_op1:
        st.markdown("**🎛️ 固定參數（所有測試都會使用）**")
        fixed_params_text = st.text_area(
            "固定參數",
            value=json.dumps(st.session_state["opt_default_params"], indent=2, ensure_ascii=False),
            height=100,
            key="fixed_params"
        )
        try:
            fixed_params = json.loads(fixed_params_text)
        except json.JSONDecodeError as e:
            st.error(f"❌ JSON 錯誤: {e}")
            fixed_params = {}

    with col_op2:
        st.markdown("**🔍 要優化的參數空間**")
        param_space_text = st.text_area(
            "參數空間（JSON）",
            value=json.dumps(st.session_state["opt_param_space"], indent=2, ensure_ascii=False),
            height=200,
            key="param_space"
        )
        try:
            param_space = json.loads(param_space_text)
        except json.JSONDecodeError as e:
            st.error(f"❌ JSON 錯誤: {e}")
            param_space = {}

    st.divider()

    col_set1, col_set2, col_set3 = st.columns(3)
    with col_set1:
        search_method = st.radio("搜尋方法", ["網格搜尋（完整）", "隨機搜尋（快速）"])
        method_code = "grid" if "網格" in search_method else "random"
    with col_set2:
        opt_metric = st.selectbox("優化目標", ["sharpe_ratio", "total_return_pct", "calmar_ratio", "profit_factor", "win_rate"])
    with col_set3:
        if method_code == "random":
            n_iter = st.number_input("迭代次數", min_value=10, max_value=2000, value=100)
        else:
            # 計算網格總數
            total_combos = 1
            for v in param_space.values():
                if isinstance(v, list):
                    total_combos *= len(v)
            st.metric("組合總數", f"{total_combos:,}")

    run_opt = st.button("🚀 開始優化", type="primary", use_container_width=True)

    if not run_opt:
        st.stop()

    if not param_space:
        st.error("請設定至少一個要優化的參數")
        st.stop()

    # 執行優化
    optimizer = ParameterOptimizer(
        strategy_runner=execute_user_strategy,
        backtest_engine_class=BacktestEngine,
        metric=opt_metric,
    )

    progress_bar = st.progress(0)
    status_text = st.empty()
    status_text.text(f"⏳ 開始{'網格' if method_code == 'grid' else '隨機'}搜尋...")

    start_time = time.time()
    if method_code == "grid":
        opt_results = optimizer.grid_search(
            df, opt_code, param_space, fixed_params,
            initial_capital, commission_pct, slippage_pct, direction_code,
        )
    else:
        opt_results = optimizer.random_search(
            df, opt_code, param_space, fixed_params,
            initial_capital, commission_pct, slippage_pct, direction_code,
            n_iter=n_iter,
        )
    progress_bar.progress(100)
    elapsed = time.time() - start_time
    status_text.text(f"✅ 完成！耗時 {elapsed:.1f} 秒，測試 {opt_results['valid_combinations']} 個有效組合")

    if not opt_results["best_params"]:
        st.error("❌ 沒有找到任何有效組合，請放寬參數空間或檢查策略代碼")
        st.stop()

    best = opt_results["best_metrics"]

    st.success(f"🎉 找到最佳參數！")

    col_r1, col_r2, col_r3, col_r4, col_r5 = st.columns(5)
    with col_r1:
        st.metric("最佳 Sharpe", f"{best.get('sharpe_ratio', 0):.2f}")
    with col_r2:
        st.metric("最佳報酬率", f"{best.get('total_return_pct', 0):+.2f}%")
    with col_r3:
        st.metric("最大回撤", f"{best.get('max_drawdown_pct', 0):.2f}%")
    with col_r4:
        st.metric("勝率", f"{best.get('win_rate', 0):.1f}%")
    with col_r5:
        st.metric("交易數", f"{best.get('n_trades', 0)}")

    # 過擬分評分
    st.subheader("🔍 過擬合風險評估")
    overfit = calculate_overfit_score(opt_results["valid_results"], top_n=10)
    col_of1, col_of2, col_of3 = st.columns([1, 1, 2])
    with col_of1:
        st.metric("過擬合評分", f"{overfit['score']:.0f}/100")
    with col_of2:
        st.metric("參數平原比", f"{overfit.get('avg_ratio', 0):.2f}")
    with col_of3:
        st.info(overfit["warning"])

    # 最佳參數
    st.subheader("🏆 最佳參數組合")
    best_params_display = {k: v for k, v in opt_results["best_params"].items() if k in param_space}
    st.json(best_params_display)

    if st.button("📋 複製到單次回測", key="copy_to_single"):
        st.session_state["strategy_code"] = opt_code
        st.session_state["current_template"] = st.session_state.get("opt_current", "")
        merged = {**fixed_params, **best_params_display}
        st.session_state["params_text"] = json.dumps(merged, indent=2, ensure_ascii=False)
        st.success("✅ 已複製到「單次回測」分頁，請切換查看")

    # Top 10 結果
    st.subheader(f"📊 Top {min(10, len(opt_results['valid_results']))} 結果")
    top_display = []
    for r in opt_results["valid_results"][:10]:
        row = {**r["params"]}
        row["Sharpe"] = r.get("sharpe_ratio", 0)
        row["報酬率 %"] = r.get("total_return_pct", 0)
        row["回撤 %"] = r.get("max_drawdown_pct", 0)
        row["勝率 %"] = r.get("win_rate", 0)
        row["交易數"] = r.get("n_trades", 0)
        row["利潤因子"] = r.get("profit_factor", 0)
        top_display.append(row)
    top_df = pd.DataFrame(top_display)
    st.dataframe(top_df, use_container_width=True, hide_index=True)

    # 2D 熱力圖（如果有兩個參數）
    if len(param_space) == 2:
        st.subheader("🔥 參數熱力圖")
        pname1, pname2 = list(param_space.keys())
        pvals1 = param_space[pname1]
        pvals2 = param_space[pname2]

        heatmap_z = np.full((len(pvals2), len(pvals1)), np.nan)
        for r in opt_results["valid_results"]:
            v1 = r["params"][pname1]
            v2 = r["params"][pname2]
            if v1 in pvals1 and v2 in pvals2:
                i = pvals1.index(v1)
                j = pvals2.index(v2)
                heatmap_z[j, i] = r.get(opt_metric, np.nan)

        fig_heat = go.Figure(data=go.Heatmap(
            z=heatmap_z, x=[str(v) for v in pvals1], y=[str(v) for v in pvals2],
            colorscale="Viridis", text=np.round(heatmap_z, 2),
            texttemplate="%{text}", colorbar=dict(title=opt_metric),
        ))
        fig_heat.update_layout(
            xaxis_title=pname1, yaxis_title=pname2,
            template="plotly_dark", height=500,
        )
        st.plotly_chart(fig_heat, use_container_width=True)


# ===========================
# 分頁 3：Walk-Forward 驗證
# ===========================
with main_tab3:
    st.header("📊 Walk-Forward 驗證")
    st.caption("""
    將資料切成多個 in-sample（訓練）與 out-of-sample（測試）區段，
    確保策略在「未見過的資料」上也能獲利，避免過擬合。

    **流程**：
    1. 將資料切 N 個區段
    2. 在前段做參數優化（in-sample）
    3. 在後段驗證（out-of-sample）
    4. 滾動前進，重複步驟 2-3
    5. 拼接所有 OOS 結果計算綜合表現
    """)

    col_w1, col_w2 = st.columns([3, 1])
    with col_w1:
        wf_sources = list_templates()
        if st.session_state.get("user_strategies"):
            wf_sources += ["── 📚 我的策略庫 ──"] + list(st.session_state["user_strategies"].keys())
        wf_template = st.selectbox("選擇策略", wf_sources, key="wf_template")
    with col_w2:
        st.write("")
        st.write("")
        if wf_template.startswith("──"):
            st.button("📥 載入策略", key="load_wf_template", disabled=True, use_container_width=True)
        elif st.button("📥 載入策略", key="load_wf_template", use_container_width=True):
            if wf_template in list_templates():
                st.session_state["wf_code"] = get_template(wf_template)
                st.session_state["wf_param_space"] = get_param_space(wf_template)
            elif wf_template in st.session_state.get("user_strategies", {}):
                st.session_state["wf_code"] = st.session_state["user_strategies"][wf_template]
                st.session_state["wf_param_space"] = {}
                st.info("自訂策略：請手動設定參數空間")
            st.session_state["wf_current"] = wf_template
            st.rerun()

    if "wf_code" not in st.session_state:
        st.session_state["wf_code"] = get_template(list_templates()[0])
        st.session_state["wf_current"] = list_templates()[0]
        st.session_state["wf_param_space"] = get_param_space(list_templates()[0])

    wf_code = st.text_area("策略代碼", value=st.session_state["wf_code"], height=200, key="wf_code_editor")

    col_wp1, col_wp2 = st.columns(2)
    with col_wp1:
        st.markdown("**🎛️ 固定參數**")
        wf_fixed_text = st.text_area(
            "固定參數",
            value=json.dumps(get_default_params(st.session_state["wf_current"]), indent=2, ensure_ascii=False),
            height=80, key="wf_fixed",
        )
        try:
            wf_fixed = json.loads(wf_fixed_text)
        except json.JSONDecodeError:
            wf_fixed = {}

    with col_wp2:
        st.markdown("**🔍 優化參數空間**")
        wf_space_text = st.text_area(
            "參數空間",
            value=json.dumps(st.session_state["wf_param_space"], indent=2, ensure_ascii=False),
            height=150, key="wf_space",
        )
        try:
            wf_param_space = json.loads(wf_space_text)
        except json.JSONDecodeError:
            wf_param_space = {}

    st.divider()

    col_ws1, col_ws2, col_ws3 = st.columns(3)
    with col_ws1:
        n_splits = st.slider("切分數量", min_value=3, max_value=10, value=5)
    with col_ws2:
        train_ratio = st.slider("訓練集佔比", min_value=0.5, max_value=0.9, value=0.7, step=0.05)
    with col_ws3:
        anchored = st.checkbox("錨定窗口（從頭開始）", value=False)
        wf_metric = st.selectbox("優化目標", ["sharpe_ratio", "total_return_pct", "calmar_ratio"],
                                  key="wf_metric")

    run_wf = st.button("🚀 執行 Walk-Forward 驗證", type="primary", use_container_width=True)

    if not run_wf:
        st.stop()

    # 判斷是否配對模式
    is_pair_wf = st.session_state.get("is_pair", False)
    pair_info_wf = st.session_state.get("pair_info", {})

    # 配對模式提示
    if is_pair_wf:
        st.info(f"🔗 配對 WF 模式：{pair_info_wf.get('symbol1')} + {pair_info_wf.get('symbol2')}")
        # 配對模式用 PairBacktestEngine
        wf_engine = PairBacktestEngine
        wf_pair_kwargs = {
            "symbol1": pair_info_wf.get("symbol1", "BTC/USDT"),
            "symbol2": pair_info_wf.get("symbol2", "ETH/USDT"),
        }
    else:
        wf_engine = BacktestEngine
        wf_pair_kwargs = {}

    validator = WalkForwardValidator(
        strategy_runner=execute_user_strategy,
        backtest_engine_class=wf_engine,
        n_splits=n_splits,
        train_ratio=train_ratio,
        anchored=anchored,
    )

    with st.spinner("⏳ Walk-Forward 驗證中（這可能需要幾分鐘）..."):
        wf_results = validator.run(
            df, wf_code, wf_param_space, wf_fixed,
            optimize_metric=wf_metric,
            initial_capital=initial_capital,
            commission=commission_pct,
            slippage=slippage_pct,
            direction=direction_code,
            is_pair=is_pair_wf,
            pair_kwargs=wf_pair_kwargs,
        )

    if "error" in wf_results:
        st.error(wf_results["error"])
        st.stop()

    st.success(f"✅ 完成 {wf_results['n_windows']} 個區段的驗證")

    # 綜合 OOS 指標
    st.subheader("📈 綜合 OOS 表現")
    oos = wf_results["combined_oos_metrics"]
    is_pair_wf = wf_results.get("is_pair", False)

    if is_pair_wf and "oos_pnl1_pct" in oos:
        # 配對模式：6 個指標
        col_oof1, col_oof2, col_oof3, col_oof4, col_oof5, col_oof6 = st.columns(6)
        with col_oof1:
            st.metric("OOS 交易數", f"{oos.get('n_oos_trades', 0)}")
        with col_oof2:
            st.metric("OOS 總報酬", f"{oos.get('oos_total_return_pct', 0):+.2f}%")
        with col_oof3:
            st.metric("OOS 勝率", f"{oos.get('oos_win_rate', 0):.1f}%")
        with col_oof4:
            st.metric("OOS 平均損益", f"{oos.get('oos_avg_pnl_pct', 0):+.2f}%")
        with col_oof5:
            st.metric(f"{pair_info_wf.get('symbol1', 'S1')} 平均", f"{oos.get('oos_pnl1_pct', 0):+.2f}%")
        with col_oof6:
            st.metric(f"{pair_info_wf.get('symbol2', 'S2')} 平均", f"{oos.get('oos_pnl2_pct', 0):+.2f}%")
    else:
        col_oof1, col_oof2, col_oof3, col_oof4, col_oof5 = st.columns(5)
        with col_oof1:
            st.metric("OOS 交易數", f"{oos.get('n_oos_trades', 0)}")
        with col_oof2:
            st.metric("OOS 總報酬", f"{oos.get('oos_total_return_pct', 0):+.2f}%")
        with col_oof3:
            st.metric("OOS 勝率", f"{oos.get('oos_win_rate', 0):.1f}%")
        with col_oof4:
            st.metric("OOS 平均損益", f"{oos.get('oos_avg_pnl_pct', 0):+.2f}%")
        with col_oof5:
            st.metric("最大單筆虧損", f"{oos.get('oos_max_single_loss_pct', 0):.2f}%")

    # 過擬合評估
    st.subheader("🎯 過擬合風險評估")
    col_od1, col_od2, col_od3 = st.columns(3)
    with col_od1:
        st.metric("平均訓練指標", f"{wf_results['avg_train_metric']:.2f}")
    with col_od2:
        st.metric("平均測試指標", f"{wf_results['avg_test_metric']:.2f}")
    with col_od3:
        deg = wf_results["degradation_pct"]
        st.metric("指標衰退率", f"{deg:+.1f}%", delta="越小越好")

    if deg < 30:
        st.success("✅ 過擬合風險低：訓練與測試指標接近，泛化能力強")
    elif deg < 60:
        st.warning("⚠️ 過擬合風險中等：訓練表現優於測試，建議保守倉位")
    else:
        st.error("🔴 過擬合風險高：策略可能在真實市場失效，建議重新設計")

    # 參數穩定度
    st.subheader("🔬 參數穩定度分析")
    stability = wf_results["parameter_stability"]
    col_st1, col_st2 = st.columns([1, 2])
    with col_st1:
        st.metric("穩定度評分", f"{stability['score']:.0f}/100")
    with col_st2:
        st.info(stability["interpretation"])

    if "details" in stability and stability["details"]:
        st.markdown("**各參數的變化**")
        stab_rows = []
        for pname, pdata in stability["details"].items():
            stab_rows.append({
                "參數": pname,
                "平均最佳值": round(pdata["mean"], 2),
                "標準差": round(pdata["std"], 2),
                "變異係數 CV": round(pdata["cv"], 3),
                "所有最佳值": str(pdata["values"]),
            })
        st.dataframe(pd.DataFrame(stab_rows), use_container_width=True, hide_index=True)

    # 每個 window 詳細結果
    st.subheader("📋 各區段詳細結果")
    wf_rows = []
    for w in wf_results["windows"]:
        row = {
            "區段": w["split_id"],
            "訓練範圍": f"{w['train_start']} → {w['train_end']}",
            "測試範圍": f"{w['test_start']} → {w['test_end']}",
        }
        if "best_params" in w:
            for pname, pval in w["best_params"].items():
                row[f"最佳 {pname}"] = pval
        row["訓練指標"] = round(w.get("train_metric", 0), 2)
        row["測試指標"] = round(w.get("test_metric", 0), 2) if w.get("test_metric") is not None else "N/A"
        row["測試報酬%"] = round(w.get("test_return", 0), 2)
        row["測試回撤%"] = round(w.get("test_drawdown", 0), 2)
        row["測試勝率%"] = round(w.get("test_win_rate", 0), 2)
        row["測試交易數"] = w.get("test_n_trades", 0)
        wf_rows.append(row)
    st.dataframe(pd.DataFrame(wf_rows), use_container_width=True, hide_index=True)


# === 頁尾 ===
st.divider()
st.caption("⚠️ 免責聲明：本工具僅供研究與教育用途。回測結果不代表未來表現。交易涉及重大風險，過去的績效不保證未來收益。")
