"""
Streamlit 回測網站主應用
支援：加密貨幣資料 (CCXT)、CSV 上傳、Python 策略代碼編寫、Walk-Forward 驗證、自動參數優化、蒙地卡羅
"""

import streamlit as st
import streamlit.components.v1 as components
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
    render_monte_carlo,
)
from utils.theme import THEMES, get_theme, get_current_theme, list_themes, theme_css


# === 頁面設定 ===
# 手機版用 query param 控制：?mobile=1 表示窄螢幕
# 預設用 expanded（讓使用者看到 sidebar）
st.set_page_config(
    page_title="加密貨幣回測實驗室",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# === 主題系統（從 session_state 讀取） ===
if "theme" not in st.session_state:
    st.session_state["theme"] = "light"

current_theme = get_theme(st.session_state["theme"])

# Google Fonts（不內嵌 @import，避免干擾系統 emoji 字體）
st.markdown(
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">',
    unsafe_allow_html=True,
)

st.markdown(theme_css(current_theme), unsafe_allow_html=True)


# === 注入浮動漢堡按鈕（用 components.html 確保 JS 一定會跑） ===
# 功能：
# 1. FAB 永遠顯示在左上角，sidebar 開啟時顯示 X（關閉），收合時顯示 ☰（開啟）
# 2. 點 FAB 切換 sidebar
# 3. 點主內容區（不含 sidebar 與 FAB）時，若 sidebar 是開啟的就收合它
# 4. 用 MutationObserver 持續監聽 DOM，確保 FAB 不會被 streamlit 重新渲染清掉
components.html(
    """
<script>
(function() {
    var ICON_MENU = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" width="22" height="22"><path d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z" fill="white"/></svg>';
    var ICON_CLOSE = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" width="22" height="22"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z" fill="white"/></svg>';

    function toggleSidebar() {
        var stBtn = window.parent.document.querySelector('button[data-testid="stBaseButton-headerNoPadding"]');
        if (stBtn) stBtn.click();
    }

    function updateFabPosition() {
        var fab = window.parent.document.getElementById('mobile-hamburger-fab');
        var sidebar = window.parent.document.querySelector('[data-testid="stSidebar"]');
        if (!fab || !sidebar) return;

        // 如果 sidebar 收合（aria-expanded=false），不覆寫 left
        // 讓 CSS 的 body.sidebar-collapsed 規則處理（left: 12px）
        var expanded = sidebar.getAttribute('aria-expanded') === 'true';
        if (!expanded) {
            fab.style.removeProperty('left');
            return;
        }

        // 用 CSS class 控制顯示/位置（CSS 處理大多數情境）
        // 這裡只處理「sidebar 寬度不是 300px」的特殊情境
        // 動態計算：sidebar 寬度 - 44 - 8 = FAB 的 left
        var sbWidth = sidebar.getBoundingClientRect().width;
        if (sbWidth > 44 + 8) {
            var fabLeft = sbWidth - 44 - 8;
            fab.style.setProperty('left', fabLeft + 'px');
        }
    }

    function updateFabIcon() {
        var btn = window.parent.document.getElementById('mobile-hamburger-fab');
        var sidebar = window.parent.document.querySelector('[data-testid="stSidebar"]');
        if (!btn || !sidebar) return;
        var expanded = sidebar.getAttribute('aria-expanded') === 'true';
        btn.innerHTML = expanded ? ICON_CLOSE : ICON_MENU;
        btn.setAttribute('aria-label', expanded ? '關閉側邊欄' : '開啟側邊欄');
        // 同步 body class（給 CSS 用來調整 FAB 位置）
        if (expanded) {
            window.parent.document.body.classList.remove('sidebar-collapsed');
        } else {
            window.parent.document.body.classList.add('sidebar-collapsed');
        }
        // 動態更新 FAB 位置
        updateFabPosition();
    }

    function createFab() {
        if (window.parent.document.getElementById('mobile-hamburger-fab')) {
            return null;  // 已存在
        }
        var btn = window.parent.document.createElement('button');
        btn.id = 'mobile-hamburger-fab';
        btn.type = 'button';
        btn.setAttribute('aria-label', '切換側邊欄');
        btn.innerHTML = ICON_MENU;
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            toggleSidebar();
        });
        return btn;
    }

    function tryInject() {
        // 等 sidebar 元素出現後再注入
        if (!window.parent.document.querySelector('[data-testid="stSidebar"]')) {
            return false;
        }
        var existing = window.parent.document.getElementById('mobile-hamburger-fab');
        if (existing) {
            updateFabIcon();
            return true;
        }
        var btn = createFab();
        if (btn) {
            window.parent.document.body.appendChild(btn);
            updateFabIcon();
            return true;
        }
        return false;
    }

    // === 全域：點主內容區 → 收合 sidebar ===
    function setupMainClickHandler() {
        if (window._fabMainClickInstalled) return;
        window._fabMainClickInstalled = true;
        window.parent.document.addEventListener('click', function(e) {
            var sidebar = window.parent.document.querySelector('[data-testid="stSidebar"]');
            if (!sidebar) return;
            var expanded = sidebar.getAttribute('aria-expanded') === 'true';
            if (!expanded) return;
            // 點到 sidebar 內、FAB 上 → 略過
            if (e.target.closest('[data-testid="stSidebar"]')) return;
            if (e.target.closest('#mobile-hamburger-fab')) return;
            // 點到 streamlit widget 內（button/input/select/textarea/a）→ 略過
            if (e.target.closest('button') ||
                e.target.closest('input') ||
                e.target.closest('select') ||
                e.target.closest('textarea') ||
                e.target.closest('a') ||
                e.target.closest('label') ||
                e.target.closest('[role="button"]') ||
                e.target.closest('[role="combobox"]') ||
                e.target.closest('[role="tab"]') ||
                e.target.closest('[role="option"]') ||
                e.target.closest('[role="listbox"]') ||
                e.target.closest('[role="menu"]') ||
                e.target.closest('[role="menuitem"]') ||
                e.target.closest('[data-baseweb="popover"]') ||
                e.target.closest('[data-baseweb="menu"]') ||
                e.target.closest('[data-baseweb="select"]')) {
                return;
            }
            // 收合 sidebar
            toggleSidebar();
        }, true);
    }

    // === 持續監聽 DOM 變化，FAB 不見就重建 ===
    function setupBodyObserver() {
        if (window._fabBodyObserverInstalled) return;
        window._fabBodyObserverInstalled = true;
        var observer = new MutationObserver(function(mutations) {
            // 檢查 FAB 是否還在
            if (!window.parent.document.getElementById('mobile-hamburger-fab')) {
                // 不見了 → 重新注入
                tryInject();
            } else {
                // 還在 → 更新圖示（sidebar 狀態可能變了）
                updateFabIcon();
            }
        });
        observer.observe(window.parent.document.body, {
            childList: true,
            subtree: false  // 只監聽 body 直接子節點
        });
        // 監聽 sidebar 的 aria-expanded 變化
        var sidebarObserver = new MutationObserver(updateFabIcon);
        function observeSidebar() {
            var sb = window.parent.document.querySelector('[data-testid="stSidebar"]');
            if (sb && !sb._fabObserved) {
                sb._fabObserved = true;
                sidebarObserver.observe(sb, { attributes: true, attributeFilter: ['aria-expanded'] });
            }
        }
        observeSidebar();
        // 持續檢查 sidebar（streamlit 重渲染時 sidebar 會被替換）
        setInterval(function() {
            observeSidebar();
            if (!window.parent.document.getElementById('mobile-hamburger-fab')) {
                tryInject();
            } else {
                updateFabPosition();  // 動態調整位置
            }
        }, 500);
    }

    // === 啟動 ===
    setupMainClickHandler();

    // 多重 retry 確保一定注入
    if (!tryInject()) {
        setTimeout(tryInject, 200);
        setTimeout(tryInject, 500);
        setTimeout(tryInject, 1000);
        setTimeout(tryInject, 2000);
        setTimeout(tryInject, 4000);
    }
    // 等 sidebar 出來後啟動 observer
    setTimeout(setupBodyObserver, 1000);
    setTimeout(setupBodyObserver, 3000);
})();
</script>
""",
    height=0,
    width=0,
)



# === 側邊欄：資料來源 ===
with st.sidebar:
    st.header("🎨 主題")

    theme_options = list_themes()
    current_idx = list(theme_options.keys()).index(st.session_state["theme"]) \
        if st.session_state["theme"] in theme_options else 0

    def _on_theme_change():
        # 從 widget 取新值
        st.session_state["theme"] = st.session_state["_theme_selector"]

    selected_theme_name = st.radio(
        "主題切換",
        options=list(theme_options.keys()),
        index=current_idx,
        key="_theme_selector",
        on_change=_on_theme_change,
        label_visibility="collapsed",
        help="切換配色主題（影響整個 app + plotly 圖表）",
        format_func=lambda tid: theme_options[tid],
    )

    st.divider()

    st.header("📊 資料來源")

    data_source = st.radio(
        "選擇資料來源",
        ["加密貨幣 (CCXT)", "上傳 CSV", "配對交易 (Pair)"],
        index=0,
    )

    is_pair_trading = (data_source == "配對交易 (Pair)")

    df = None
    data_info = ""

    if data_source == "加密貨幣 (CCXT)":
        exchange_ids = get_available_exchanges()
        exchange_labels = {eid: get_exchange_display_name(eid) for eid in exchange_ids}
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
            default_sym = get_default_symbol(selected_exchange)
            symbol = st.text_input("交易對", value=default_sym, key="symbol_input")

        if selected_exchange == "bingx":
            popular = get_bingx_popular_symbols()
            with st.expander("⭐ BingX 熱門交易對", expanded=False):
                st.caption("點擊按鈕快速填入交易對")
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
                        st.session_state["is_pair"] = False
                        st.success(f"✅ 從 {get_exchange_display_name(selected_exchange)} 抓取 {len(df):,} 根 K 線")
                    else:
                        st.error("❌ 抓取失敗：無資料")
                except ValueError as e:
                    st.error(f"❌ 參數錯誤: {e}")
                except ConnectionError as e:
                    st.error(f"❌ 連線問題: {e}")
                except RuntimeError as e:
                    st.error(f"❌ 交易所錯誤: {e}")
                except Exception as e:
                    st.error(f"❌ 未預期錯誤 ({type(e).__name__}): {e}")

        # 測試資料按鈕：生成固定 K 線，不用網路抓取
        if st.button("🧪 一鍵測試資料", use_container_width=True, help="生成 500 根固定 seed 的模擬 K 線，無需網路"):
            try:
                np.random.seed(42)
                n = 500
                # 用幾何布朗運動模擬 BTC 價格
                base_price = 30000
                returns = np.random.normal(0.0005, 0.02, n)
                close = base_price * np.exp(np.cumsum(returns))
                # 生成對應的 OHLCV
                high = close * (1 + np.abs(np.random.normal(0, 0.005, n)))
                low = close * (1 - np.abs(np.random.normal(0, 0.005, n)))
                open_ = np.roll(close, 1)
                open_[0] = base_price
                volume = np.random.uniform(100, 1000, n)
                test_df = pd.DataFrame({
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }, index=pd.date_range("2024-01-01", periods=n, freq="1D"))
                st.session_state["df"] = test_df
                st.session_state["is_pair"] = False
                st.session_state["symbol"] = "TEST/USDT"
                st.session_state["exchange"] = "synthetic"
                st.session_state["timeframe"] = "1d"
                st.session_state.pop("pair_info", None)
                st.success(f"✅ 已生成 {len(test_df):,} 根測試 K 線（價格 ${close[0]:,.0f} → ${close[-1]:,.0f}）")
                st.rerun()
            except Exception as e:
                st.error(f"❌ 生成測試資料失敗: {e}")

    else:  # CSV 上傳 or 配對交易
        if data_source == "上傳 CSV":
            uploaded = st.file_uploader("上傳 CSV 檔案", type=["csv"])
            if uploaded is not None:
                try:
                    df = load_csv_data(uploaded)
                    if df is not None and not df.empty:
                        st.session_state["df"] = df
                        st.session_state["is_pair"] = False
                        st.success(f"✅ 載入 {len(df):,} 筆資料")
                except Exception as e:
                    st.error(f"❌ {e}")

        elif data_source == "配對交易 (Pair)":
            st.caption("📊 配對交易：同時下兩個反向部位")

            pair_templates = get_pair_templates()
            pair_labels = {p["name"]: p for p in pair_templates}
            selected_pair_name = st.selectbox(
                "選擇配對組合",
                list(pair_labels.keys()),
                index=0,
            )
            selected_pair = pair_labels[selected_pair_name]
            st.caption(f"📈 {selected_pair['symbol1']} vs {selected_pair['symbol2']}")

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

    if "df" in st.session_state and df is None:
        df = st.session_state["df"]
        is_pair = st.session_state.get("is_pair", False)
        if is_pair:
            pair_info = st.session_state.get("pair_info", {})
            st.info(f"📦 配對：{pair_info.get('symbol1', '?')} + {pair_info.get('symbol2', '?')} ({len(df):,} 根)")
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

    st.header("📚 策略管理")

    if "user_strategies" not in st.session_state:
        st.session_state["user_strategies"] = {}

    with st.expander("📤 上傳 / 貼上策略", expanded=False):
        st.caption("三種方式加入策略到「我的策略庫」")

        st.markdown("**① 上傳 .py 檔案**")
        uploaded_files = st.file_uploader(
            "選擇 .py 檔（可多選）",
            type=["py"],
            accept_multiple_files=True,
            key="strategy_uploader",
        )
        if uploaded_files:
            for f in uploaded_files:
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

        st.markdown("**② 貼上 Python 代碼**")
        pasted_code = st.text_area(
            "貼上策略代碼", height=120, key="pasted_strategy",
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

    st.header("⚙️ 回測參數")
    initial_capital = st.number_input("初始資金 (USDT)", min_value=100.0, value=10000.0, step=1000.0)
    commission_pct = st.number_input("手續費 (%)", min_value=0.0, max_value=5.0, value=0.1, step=0.05) / 100
    slippage_pct = st.number_input("滑點 (%)", min_value=0.0, max_value=2.0, value=0.05, step=0.01) / 100

    # direction 由 strategy 自動決定（不讓用戶選）：
    # - 如果 strategy 回傳 4 個 series (long_entries, long_exits, short_entries, short_exits)
    #   → 自動用 long_short 模式
    # - 否則 → 預設 long 模式
    # 這裡先預設 long，執行回測時再依 strategy 結果自動切換
    direction_code = "long"

    use_sl_tp = st.checkbox("啟用停損/停利")
    if use_sl_tp:
        col5, col6 = st.columns(2)
        with col5:
            stop_loss = st.number_input("停損 (%)", min_value=0.1, max_value=50.0, value=2.0, step=0.5) / 100
        with col6:
            take_profit = st.number_input("停利 (%)", min_value=0.1, max_value=100.0, value=4.0, step=0.5) / 100
    else:
        stop_loss = None
        take_profit = None

# === 主區域：先檢查資料 ===
if df is None or df.empty:
    st.info("👈 請從左側選擇資料來源並載入資料")
    st.markdown("""
    ### 🚀 快速開始

    1. **選擇資料來源**（左側）
       - 加密貨幣：自動從 Binance、OKX、Bybit、BingX 等交易所抓取
       - CSV：上傳自己的 OHLCV 資料
       - 配對交易：BTC/ETH 等配對組合
    2. **選擇功能分頁**（下方）

    ### 🧠 內建 15 種策略範本
    SMA 交叉、RSI、布林通道、MACD、網格、海龜、KDJ、CCI、Donchian、TEMA、VWAP、OBV、一目均衡表、Parabolic SAR、BTC/ETH 比率配對
    """)
    st.stop()


# 取得配對資訊
is_pair = st.session_state.get("is_pair", False)
pair_info = st.session_state.get("pair_info", {})


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

    col_src1, col_src2 = st.columns([3, 1])
    with col_src1:
        all_sources = ["（自訂）"] + list_templates()
        if st.session_state.get("user_strategies"):
            all_sources += ["── 📚 我的策略庫 ──"] + list(st.session_state["user_strategies"].keys())

        # 計算 selectbox 當前 index
        prev_template = st.session_state.get("current_template", "（自訂）")
        prev_idx = all_sources.index(prev_template) if prev_template in all_sources else 0

        template_choice = st.selectbox(
            "選擇策略來源",
            all_sources,
            index=prev_idx,
            key="template_select",
            help="選擇後會自動載入對應策略代碼",
        )

    # 自動載入：選擇變了就立即更新 strategy_code
    if not template_choice.startswith("──") and template_choice != "（自訂）":
        if st.session_state.get("current_template") != template_choice:
            if template_choice in list_templates():
                new_code = get_template(template_choice)
            elif template_choice in st.session_state.get("user_strategies", {}):
                new_code = st.session_state["user_strategies"][template_choice]
            else:
                new_code = None
            if new_code is not None:
                st.session_state["strategy_code"] = new_code
                st.session_state["current_template"] = template_choice
                # 同步更新 text_area 的 widget state，否則 key 已存在會忽略新 value
                st.session_state["strategy_code_editor"] = new_code
                # 同步更新策略參數（JSON 格式）
                default_p = get_default_params(template_choice)
                st.session_state["params_text"] = json.dumps(default_p, indent=2, ensure_ascii=False)
                st.rerun()

    with col_src2:
        st.write("")
        if template_choice.startswith("──"):
            st.button("📥 載入", key="load_template", disabled=True, use_container_width=True)
        else:
            if st.button("🔄 重新載入", key="load_template", use_container_width=True,
                         help="重新從範本載入（會覆蓋目前編輯的代碼）"):
                if template_choice in list_templates():
                    new_code = get_template(template_choice)
                elif template_choice in st.session_state.get("user_strategies", {}):
                    new_code = st.session_state["user_strategies"][template_choice]
                else:
                    new_code = None
                if new_code is not None:
                    st.session_state["strategy_code"] = new_code
                    st.session_state["current_template"] = template_choice
                    st.session_state["strategy_code_editor"] = new_code
                    # 同步更新策略參數（JSON 格式）
                    default_p = get_default_params(template_choice)
                    st.session_state["params_text"] = json.dumps(default_p, indent=2, ensure_ascii=False)
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
        current_t = st.session_state.get("current_template", "")
        if current_t and current_t != "（自訂）":
            default_params = get_default_params(current_t)
        else:
            default_params = {"period": 20}
        default_json = json.dumps(default_params, indent=2, ensure_ascii=False)

        # 確保 params_text 與當前策略一致
        # session_state["params_text"] 會在切換策略時被自動設定
        params_text = st.text_area("參數", value=st.session_state.get("params_text", default_json), height=100, key="params_text")
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

    # 關鍵：只在按下按鈕時才執行後續，否則「自然結束」這個 tab
    # 方向由 strategy 自動決定（不讓用戶選）：
    # - 如果 strategy 回傳 4 個 series (long_entries, long_exits, short_entries, short_exits)
    #   → 自動用 long_short 模式
    # - 如果 strategy 回傳 2 個 series (entries, exits)
    #   → 預設 long 模式
    # 透過檢查 long_entries/short_entries 是否有訊號來自動選擇
    if not run_single:
        st.info("👆 點擊「▶️ 執行回測」開始分析")
    else:
        # 執行策略（最外層 try 確保任何錯誤都不會導致整個 app 崩潰）
        try:
            result = execute_user_strategy(strategy_code, df, strategy_params)
            # 顯示 debug 資訊（只顯示長度，不暴露內容）
            result_type = type(result).__name__
            result_len = len(result) if hasattr(result, '__len__') else 'N/A'
            # 防護：確保 result 是 7-tuple
            if not isinstance(result, tuple) or len(result) != 7:
                st.warning(f"⚠️ 策略回傳了 {result_len} 個元素（type={result_type}），自動補齊為 7 個")
                empty_series = pd.Series(False, index=df.index)
                result_list = list(result) if isinstance(result, (tuple, list)) else []
                while len(result_list) < 7:
                    result_list.append(empty_series)
                result = tuple(result_list[:7])
            entries, exits, err, long_entries, long_exits, short_entries, short_exits = result
        except Exception as e:
            st.error(f"❌ 策略執行失敗: {type(e).__name__}: {e}")
            st.stop()

        # 自動判斷方向：策略有 short 訊號 → 用 long_short 模式
        # 判斷依據：short_entries 或 short_exits 是否有任何 True
        if short_entries is not None and short_entries.any():
            actual_direction = "long_short"
        else:
            actual_direction = "long"

        if err:
            st.error(err)
        elif actual_direction == "long_short" and not long_entries.any() and not short_entries.any():
            st.warning("⚠️ 策略沒有產生任何進場訊號（long/short 都沒有）")
        elif actual_direction == "long" and not entries.any():
            st.warning("⚠️ 策略沒有產生任何進場訊號")
        else:
            # 跑回測
            with st.spinner("執行回測中..."):
                if is_pair and pair_info:
                    pair_direction = "pair_long" if actual_direction == "long" else "pair_short"
                    engine = PairBacktestEngine(
                        df,
                        symbol1=pair_info.get("symbol1", "BTC/USDT"),
                        symbol2=pair_info.get("symbol2", "ETH/USDT"),
                        initial_capital=initial_capital,
                        commission=commission_pct,
                        slippage=slippage_pct,
                    )
                    try:
                        results = engine.run(entries, exits, direction=pair_direction,
                                              stop_loss=stop_loss, take_profit=take_profit)
                    except Exception as e:
                        st.error(f"❌ 配對回測引擎錯誤: {type(e).__name__}: {e}")
                        st.stop()
                else:
                    engine = BacktestEngine(
                        df, initial_capital=initial_capital,
                        commission=commission_pct, slippage=slippage_pct,
                    )
                    try:
                        results = engine.run(
                            entries, exits, direction=actual_direction,
                            stop_loss=stop_loss, take_profit=take_profit,
                            long_entries=long_entries,
                            long_exits=long_exits,
                            short_entries=short_entries,
                            short_exits=short_exits,
                        )
                    except Exception as e:
                        st.error(f"❌ 回測引擎錯誤: {type(e).__name__}: {e}")
                        st.stop()

            result_df = results["data"]
            trades = results["trades"]
            metrics = results["metrics"]

            # 存到 session_state，讓切到 MC tab 後還能使用
            st.session_state["bt_result_df"] = result_df
            st.session_state["bt_trades"] = trades
            st.session_state["bt_metrics"] = metrics
            st.session_state["bt_is_pair"] = is_pair and bool(pair_info)
            st.session_state["bt_pair_info"] = pair_info

            if "error" in metrics:
                st.warning(metrics["error"])
            else:
                # 5 分頁結果顯示
                result_tab1, result_tab2, result_tab3, result_tab4, result_tab5 = st.tabs([
                    "📊 Overview",
                    "📈 Performance Summary",
                    "📋 List of Trades",
                    "🕯️ Charts",
                    "🎲 蒙地卡羅",
                ])

                with result_tab1:
                    render_overview(metrics, result_df, initial_capital)

                with result_tab2:
                    render_performance_summary(trades, metrics)

                with result_tab3:
                    render_list_of_trades(trades)

                with result_tab4:
                    render_charts(result_df, trades)

                with result_tab5:
                    render_monte_carlo(initial_capital, trades)

    # 即使沒按「▶️ 執行回測」，若有先前結果 → 顯示結果 tabs
    if not run_single and "bt_result_df" in st.session_state and st.session_state.get("bt_trades"):
        result_df = st.session_state["bt_result_df"]
        trades = st.session_state["bt_trades"]
        metrics = st.session_state["bt_metrics"]

        st.info("📊 顯示先前的回測結果（如需重新執行請按「▶️ 執行回測」）")

        result_tab1, result_tab2, result_tab3, result_tab4, result_tab5 = st.tabs([
            "📊 Overview",
            "📈 Performance Summary",
            "📋 List of Trades",
            "🕯️ Charts",
            "🎲 蒙地卡羅",
        ])

        with result_tab1:
            render_overview(metrics, result_df, initial_capital)

        with result_tab2:
            render_performance_summary(trades, metrics)

        with result_tab3:
            render_list_of_trades(trades)

        with result_tab4:
            render_charts(result_df, trades)

        with result_tab5:
            render_monte_carlo(initial_capital, trades)


# ===========================
# 分頁 2：自動參數優化
# ===========================
with main_tab2:
    st.header("🤖 自動參數優化")
    st.caption("自動測試所有參數組合，找出最佳表現。")

    col_o1, col_o2 = st.columns([3, 1])
    with col_o1:
        opt_sources = list_templates()
        if st.session_state.get("user_strategies"):
            opt_sources += ["── 📚 我的策略庫 ──"] + list(st.session_state["user_strategies"].keys())
        # 計算 selectbox 當前 index
        prev_opt = st.session_state.get("opt_current", list_templates()[0])
        opt_idx = opt_sources.index(prev_opt) if prev_opt in opt_sources else 0
        opt_template = st.selectbox(
            "選擇策略",
            opt_sources,
            index=opt_idx,
            key="opt_template",
            help="選擇後會自動載入對應策略",
        )

        # 自動載入
        if not opt_template.startswith("──"):
            if st.session_state.get("opt_current") != opt_template:
                if opt_template in list_templates():
                    new_code = get_template(opt_template)
                    new_space = get_param_space(opt_template)
                    new_default = get_default_params(opt_template)
                elif opt_template in st.session_state.get("user_strategies", {}):
                    new_code = st.session_state["user_strategies"][opt_template]
                    new_space = {}
                    new_default = {}
                else:
                    new_code = None
                if new_code is not None:
                    st.session_state["opt_code"] = new_code
                    st.session_state["opt_param_space"] = new_space
                    st.session_state["opt_default_params"] = new_default
                    st.session_state["opt_current"] = opt_template
                    # 同步更新 widget state（text_area 已存在需直接設 session_state[key]）
                    st.session_state["opt_code_editor"] = new_code
                    st.session_state["fixed_params"] = json.dumps(new_default, indent=2, ensure_ascii=False)
                    st.session_state["param_space"] = json.dumps(new_space, indent=2, ensure_ascii=False)
                    st.rerun()

    with col_o2:
        st.write("")
        st.write("")
        if opt_template.startswith("──"):
            st.button("📥 載入", key="load_opt_template", disabled=True, use_container_width=True)
        else:
            if st.button("🔄 重新載入", key="load_opt_template", use_container_width=True,
                         help="重新從範本載入（會覆蓋目前編輯的代碼）"):
                if opt_template in list_templates():
                    new_code = get_template(opt_template)
                    new_space = get_param_space(opt_template)
                    new_default = get_default_params(opt_template)
                elif opt_template in st.session_state.get("user_strategies", {}):
                    new_code = st.session_state["user_strategies"][opt_template]
                    new_space = {}
                    new_default = {}
                else:
                    new_code = None
                if new_code is not None:
                    st.session_state["opt_code"] = new_code
                    st.session_state["opt_param_space"] = new_space
                    st.session_state["opt_default_params"] = new_default
                    st.session_state["opt_current"] = opt_template
                    st.session_state["opt_code_editor"] = new_code
                    # 同步更新 JSON widget state
                    st.session_state["fixed_params"] = json.dumps(new_default, indent=2, ensure_ascii=False)
                    st.session_state["param_space"] = json.dumps(new_space, indent=2, ensure_ascii=False)
                    st.rerun()

    if "opt_code" not in st.session_state:
        st.session_state["opt_code"] = get_template(list_templates()[0])
        st.session_state["opt_current"] = list_templates()[0]
        st.session_state["opt_param_space"] = get_param_space(list_templates()[0])
        st.session_state["opt_default_params"] = get_default_params(list_templates()[0])

    opt_code = st.text_area("策略代碼（可編輯）", value=st.session_state["opt_code"],
                              height=250, key="opt_code_editor")

    # === 可見性（放在外面，label + widget 並排格式）===
    st.markdown("**👁️ 可見性**")
    vis_left, vis_right = st.columns([1, 3])
    with vis_left:
        st.markdown("<div style='padding-top: 12px; padding-right: 8px; text-align: right;'>搜尋方法</div>", unsafe_allow_html=True)
    with vis_right:
        search_method = st.radio(
            "搜尋方法",
            ["網格搜尋（完整）", "隨機搜尋（快速）"],
            key="opt_search_method",
            label_visibility="collapsed"
        )
    method_code = "grid" if "網格" in search_method else "random"

    vis_left2, vis_right2 = st.columns([1, 3])
    with vis_left2:
        st.markdown("<div style='padding-top: 12px; padding-right: 8px; text-align: right;'>優化目標</div>", unsafe_allow_html=True)
    with vis_right2:
        opt_metric = st.selectbox(
            "優化目標",
            ["sharpe_ratio", "total_return_pct", "calmar_ratio", "profit_factor", "win_rate"],
            key="opt_metric",
            label_visibility="collapsed"
        )

    if method_code == "random":
        vis_left3, vis_right3 = st.columns([1, 3])
        with vis_left3:
            st.markdown("<div style='padding-top: 12px; padding-right: 8px; text-align: right;'>迭代次數</div>", unsafe_allow_html=True)
        with vis_right3:
            n_iter = st.number_input("迭代次數", min_value=10, max_value=2000, value=100,
                                     key="opt_n_iter", label_visibility="collapsed")
    # 組合總數會在 tabs 之後（param_space 已被讀取）動態計算並顯示

    st.divider()

    # === 兩個 tab：輸入（固定參數）/ 模式（參數空間）===
    tab_input, tab_mode = st.tabs(["🎛️ 輸入", "🔍 模式"])

    with tab_input:
        st.caption("固定參數（所有測試都會使用）")
        if "fixed_params" not in st.session_state:
            st.session_state["fixed_params"] = json.dumps(
                st.session_state.get("opt_default_params", {}), indent=2, ensure_ascii=False
            )
        fixed_params_text = st.text_area(
            "固定參數（JSON）",
            value=st.session_state["fixed_params"],
            height=250,
            key="fixed_params",
            label_visibility="collapsed"
        )
        try:
            fixed_params = json.loads(fixed_params_text)
        except json.JSONDecodeError as e:
            st.error(f"❌ JSON 錯誤: {e}")
            fixed_params = {}

    with tab_mode:
        st.caption("要優化的參數空間（每個 key 是參數名，value 是候選值清單）")
        if "param_space" not in st.session_state:
            st.session_state["param_space"] = json.dumps(
                st.session_state.get("opt_param_space", {}), indent=2, ensure_ascii=False
            )
        param_space_text = st.text_area(
            "參數空間（JSON）",
            value=st.session_state["param_space"],
            height=350,
            key="param_space",
            label_visibility="collapsed"
        )
        try:
            param_space = json.loads(param_space_text)
        except json.JSONDecodeError as e:
            st.error(f"❌ JSON 錯誤: {e}")
            param_space = {}

    # 動態更新組合總數（在 tabs 之後，這樣 param_space 已被讀取）
    if method_code != "random":
        # 重新算 total_combos 顯示
        if isinstance(param_space, dict) and param_space:
            _total = 1
            for v in param_space.values():
                if isinstance(v, list):
                    _total *= len(v)
            st.metric("組合總數", f"{_total:,}")

    run_opt = st.button("🚀 開始優化", type="primary", use_container_width=True)

    if not run_opt:
        st.info("👆 設定參數空間後點擊「🚀 開始優化」")
    elif not param_space:
        st.error("請設定至少一個要優化的參數")
    else:
        optimizer = ParameterOptimizer(
            strategy_runner=execute_user_strategy,
            backtest_engine_class=BacktestEngine,
            metric=opt_metric,
        )

        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text(f"⏳ 開始{'網格' if method_code == 'grid' else '隨機'}搜尋...")

        start_time = time.time()
        try:
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
        except Exception as e:
            progress_bar.progress(100)
            status_text.text(f"❌ 優化失敗")
            st.error(f"❌ 參數優化錯誤: {type(e).__name__}: {e}")
            st.exception(e)
            st.stop()
        progress_bar.progress(100)
        elapsed = time.time() - start_time
        status_text.text(f"✅ 完成！耗時 {elapsed:.1f} 秒，測試 {opt_results['valid_combinations']} 個有效組合")

        if not opt_results["best_params"]:
            st.error("❌ 沒有找到任何有效組合，請放寬參數空間或檢查策略代碼")
        else:
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

            st.subheader("🔍 過擬合風險評估")
            overfit = calculate_overfit_score(opt_results["valid_results"], top_n=10)
            col_of1, col_of2, col_of3 = st.columns([1, 1, 2])
            with col_of1:
                st.metric("過擬合評分", f"{overfit['score']:.0f}/100")
            with col_of2:
                st.metric("參數平原比", f"{overfit.get('avg_ratio', 0):.2f}")
            with col_of3:
                st.info(overfit["warning"])

            st.subheader("🏆 最佳參數組合")
            best_params_display = {k: v for k, v in opt_results["best_params"].items() if k in param_space}
            st.json(best_params_display)

            if st.button("📋 複製到單次回測", key="copy_to_single"):
                st.session_state["strategy_code"] = opt_code
                st.session_state["current_template"] = st.session_state.get("opt_current", "")
                merged = {**fixed_params, **best_params_display}
                st.session_state["params_text"] = json.dumps(merged, indent=2, ensure_ascii=False)
                st.success("✅ 已複製到「單次回測」分頁，請切換查看")

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
    """)

    col_w1, col_w2 = st.columns([3, 1])
    with col_w1:
        wf_sources = list_templates()
        if st.session_state.get("user_strategies"):
            wf_sources += ["── 📚 我的策略庫 ──"] + list(st.session_state["user_strategies"].keys())
        # 計算 selectbox 當前 index
        prev_wf = st.session_state.get("wf_current", list_templates()[0])
        wf_idx = wf_sources.index(prev_wf) if prev_wf in wf_sources else 0
        wf_template = st.selectbox(
            "選擇策略",
            wf_sources,
            index=wf_idx,
            key="wf_template",
            help="選擇後會自動載入對應策略",
        )

        # 自動載入
        if not wf_template.startswith("──"):
            if st.session_state.get("wf_current") != wf_template:
                if wf_template in list_templates():
                    new_code = get_template(wf_template)
                    new_space = get_param_space(wf_template)
                    new_default = get_default_params(wf_template)
                elif wf_template in st.session_state.get("user_strategies", {}):
                    new_code = st.session_state["user_strategies"][wf_template]
                    new_space = {}
                    new_default = {}
                else:
                    new_code = None
                if new_code is not None:
                    st.session_state["wf_code"] = new_code
                    st.session_state["wf_param_space"] = new_space
                    st.session_state["wf_current"] = wf_template
                    st.session_state["wf_code_editor"] = new_code
                    # 同步更新 JSON widget state
                    st.session_state["wf_fixed"] = json.dumps(new_default, indent=2, ensure_ascii=False)
                    st.session_state["wf_space"] = json.dumps(new_space, indent=2, ensure_ascii=False)
                    st.rerun()

    with col_w2:
        st.write("")
        st.write("")
        if wf_template.startswith("──"):
            st.button("📥 載入", key="load_wf_template", disabled=True, use_container_width=True)
        else:
            if st.button("🔄 重新載入", key="load_wf_template", use_container_width=True,
                         help="重新從範本載入（會覆蓋目前編輯的代碼）"):
                if wf_template in list_templates():
                    new_code = get_template(wf_template)
                    new_space = get_param_space(wf_template)
                    new_default = get_default_params(wf_template)
                elif wf_template in st.session_state.get("user_strategies", {}):
                    new_code = st.session_state["user_strategies"][wf_template]
                    new_space = {}
                    new_default = {}
                else:
                    new_code = None
                if new_code is not None:
                    st.session_state["wf_code"] = new_code
                    st.session_state["wf_param_space"] = new_space
                    st.session_state["wf_current"] = wf_template
                    st.session_state["wf_code_editor"] = new_code
                    # 同步更新 JSON widget state
                    st.session_state["wf_fixed"] = json.dumps(new_default, indent=2, ensure_ascii=False)
                    st.session_state["wf_space"] = json.dumps(new_space, indent=2, ensure_ascii=False)
                    st.rerun()

    if "wf_code" not in st.session_state:
        st.session_state["wf_code"] = get_template(list_templates()[0])
        st.session_state["wf_current"] = list_templates()[0]
        st.session_state["wf_param_space"] = get_param_space(list_templates()[0])

    wf_code = st.text_area("策略代碼", value=st.session_state["wf_code"], height=200, key="wf_code_editor")

    # === 可見性（放在外面，label + widget 並排格式）===
    st.markdown("**👁️ 可見性**")
    vis_left1, vis_right1 = st.columns([1, 3])
    with vis_left1:
        st.markdown("<div style='padding-top: 12px; padding-right: 8px; text-align: right;'>切分數量</div>", unsafe_allow_html=True)
    with vis_right1:
        n_splits = st.slider("切分數量", min_value=3, max_value=10, value=5, key="wf_n_splits",
                              label_visibility="collapsed")

    vis_left2, vis_right2 = st.columns([1, 3])
    with vis_left2:
        st.markdown("<div style='padding-top: 12px; padding-right: 8px; text-align: right;'>訓練集佔比</div>", unsafe_allow_html=True)
    with vis_right2:
        train_ratio = st.slider("訓練集佔比", min_value=0.5, max_value=0.9, value=0.7, step=0.05,
                                 key="wf_train_ratio", label_visibility="collapsed")

    vis_left3, vis_right3 = st.columns([1, 3])
    with vis_left3:
        st.markdown("<div style='padding-top: 12px; padding-right: 8px; text-align: right;'>錨定窗口</div>", unsafe_allow_html=True)
    with vis_right3:
        anchored = st.checkbox("錨定窗口（從頭開始）", value=False, key="wf_anchored",
                                label_visibility="collapsed")

    vis_left4, vis_right4 = st.columns([1, 3])
    with vis_left4:
        st.markdown("<div style='padding-top: 12px; padding-right: 8px; text-align: right;'>優化目標</div>", unsafe_allow_html=True)
    with vis_right4:
        wf_metric = st.selectbox(
            "優化目標",
            ["sharpe_ratio", "total_return_pct", "calmar_ratio"],
            key="wf_metric",
            label_visibility="collapsed"
        )

    st.divider()

    # === 兩個 tab：輸入（固定參數）/ 模式（參數空間）===
    wf_tab_input, wf_tab_mode = st.tabs(["🎛️ 輸入", "🔍 模式"])

    with wf_tab_input:
        st.caption("固定參數")
        if "wf_fixed" not in st.session_state:
            st.session_state["wf_fixed"] = json.dumps(
                get_default_params(st.session_state.get("wf_current", list_templates()[0])),
                indent=2, ensure_ascii=False
            )
        wf_fixed_text = st.text_area(
            "固定參數（JSON）",
            value=st.session_state["wf_fixed"],
            height=250, key="wf_fixed",
            label_visibility="collapsed"
        )
        try:
            wf_fixed = json.loads(wf_fixed_text)
        except json.JSONDecodeError:
            wf_fixed = {}

    with wf_tab_mode:
        st.caption("優化參數空間（每個 key 是參數名，value 是候選值清單）")
        if "wf_space" not in st.session_state:
            st.session_state["wf_space"] = json.dumps(
                st.session_state.get("wf_param_space", {}),
                indent=2, ensure_ascii=False
            )
        wf_space_text = st.text_area(
            "參數空間（JSON）",
            value=st.session_state["wf_space"],
            height=350, key="wf_space",
            label_visibility="collapsed"
        )
        try:
            wf_param_space = json.loads(wf_space_text)
        except json.JSONDecodeError:
            wf_param_space = {}

    run_wf = st.button("🚀 執行 Walk-Forward 驗證", type="primary", use_container_width=True)

    if not run_wf:
        st.info("👆 設定參數後點擊「🚀 執行 Walk-Forward 驗證」")
    else:
        # 配對模式設定
        if is_pair and pair_info:
            st.info(f"🔗 配對 WF 模式：{pair_info.get('symbol1')} + {pair_info.get('symbol2')}")
            wf_engine = PairBacktestEngine
            wf_pair_kwargs = {
                "symbol1": pair_info.get("symbol1", "BTC/USDT"),
                "symbol2": pair_info.get("symbol2", "ETH/USDT"),
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
                is_pair=is_pair and bool(pair_info),
                pair_kwargs=wf_pair_kwargs,
            )

        if "error" in wf_results:
            st.error(wf_results["error"])
        else:
            st.success(f"✅ 完成 {wf_results['n_windows']} 個區段的驗證")

            st.subheader("📈 綜合 OOS 表現")
            oos = wf_results["combined_oos_metrics"]
            is_pair_wf = wf_results.get("is_pair", False)

            if is_pair_wf and "oos_pnl1_pct" in oos:
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
                    st.metric(f"{pair_info.get('symbol1', 'S1')} 平均", f"{oos.get('oos_pnl1_pct', 0):+.2f}%")
                with col_oof6:
                    st.metric(f"{pair_info.get('symbol2', 'S2')} 平均", f"{oos.get('oos_pnl2_pct', 0):+.2f}%")
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
                st.error("🔴 過擬合風險高：策略可能在真實市場失效")

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
st.caption("⚠️ 免責聲明：本工具僅供研究與教育用途。回測結果不代表未來表現。")
