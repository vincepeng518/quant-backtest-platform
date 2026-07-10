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
from utils.walk_forward import WalkForwardValidator, timeseries_split_validate
from utils.optimizer import ParameterOptimizer, calculate_overfit_score
from utils.optuna_optimizer import OptunaOptimizer
from utils.objective_builder import list_objectives, get_objective_fn
from utils.param_space_editor import render_param_space_editor, get_default_specs_for_strategy
from utils.perturbation import PerturbationTester
from utils.seed import set_global_seed
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
from utils.impeccable import (
    section_header, step_indicator, status_pill, empty_state, welcome_panel,
)
from utils.theme import get_theme, theme_css


# === 頁面設定 ===
# 手機版用 query param 控制：?mobile=1 表示窄螢幕
# 預設用 expanded（讓使用者看到 sidebar）
st.set_page_config(
    page_title="加密貨幣回測實驗室",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


# === 自動偵測並套用主題 ===
# v8 改進：完全交由 Streamlit 原生主題機制處理
# 不再自製 FAB / radio 切換；<html data-theme> 由 JS 自動跟隨
# Streamlit 的 .stApp theme 屬性（colorScheme: "light" | "dark"）
current_theme = get_theme("light")  # CSS 變數用 light 作為預設渲染（兩組都會輸出，CSS 自動切換）

# Google Fonts（不內嵌 @import，避免干擾系統 emoji 字體）
st.markdown(
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">',
    unsafe_allow_html=True,
)

# 自動偵測 Streamlit 當前主題 + 系統偏好 → 套用到 <html data-theme>
# 這樣 CSS variables 會自動切換，無需用戶手動操作
st.markdown(
    """
<script>
(function() {
    function applyThemeFromStreamlit() {
        try {
            // 讀取 Streamlit 套用於 <body> 的 data-theme 屬性
            // Streamlit 1.30+ 在 .stApp 容器上設置 colorScheme 樣式
            var app = document.querySelector('.stApp');
            var computedDark = false;
            if (app) {
                var cs = window.getComputedStyle(app);
                var bg = cs.getPropertyValue('background-color') || '';
                // Streamlit dark theme 的背景色偏深（< 60 亮度）
                if (bg) {
                    var m = bg.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                    if (m) {
                        var brightness = (parseInt(m[1]) + parseInt(m[2]) + parseInt(m[3])) / 3;
                        if (brightness < 60) computedDark = true;
                    }
                }
            }
            var theme = computedDark ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', theme);
        } catch (e) {
            // 兜底：跟隨系統
            var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
            document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
        }
    }
    applyThemeFromStreamlit();
    // 監聽 Streamlit 主題變化（用戶用右上角 menu 切換時觸發）
    setTimeout(applyThemeFromStreamlit, 200);
    setTimeout(applyThemeFromStreamlit, 600);
    // 監聽系統主題變化
    try {
        var mq = window.matchMedia('(prefers-color-scheme: dark)');
        if (mq && mq.addEventListener) {
            mq.addEventListener('change', applyThemeFromStreamlit);
        }
    } catch (e) {}
})();
</script>
""",
    unsafe_allow_html=True,
)

st.markdown(theme_css(current_theme), unsafe_allow_html=True)


# === 快速開始步進器狀態管理 ===
# 0 = 步驟 1「選擇資料來源」（初始）
# 1 = 步驟 2「載入資料」（成功後自動 +1）
# 2 = 步驟 3「選擇策略」
# 3 = 步驟 4「執行回測」
# 4 = 步驟 5「檢視結果」
# 用 session_state 動態管理，當用戶在側邊欄載入資料成功後自動前進
if "current_step" not in st.session_state:
    st.session_state["current_step"] = 0

# v10 改進：每個 rerun 開始時重置 _has_rendered_overview_this_run 旗標
# 避免下方 else/if 兩處都呼叫 render_overview（會觸發 DuplicateElementKey）
# 旗標在「剛執行完回測」的 else 分支內設為 True
if "_has_rendered_overview_this_run" in st.session_state:
    del st.session_state["_has_rendered_overview_this_run"]


# === 注入 CSS：防止平板鍵盤在 selectbox 點擊時彈出 ===
# 問題：Streamlit 1.59 用 React Aria Components 渲染 selectbox
#       內含 <input role="combobox" type="text">，
#       在 iPad/平板上 focus 時會觸發虛擬鍵盤
# 解法：
#   1) 平板：input 仍可接收事件（讓 React Aria 觸發 dropdown）
#      但 focus 後 JS 立即 blur，避免觸發虛擬鍵盤
#   2) 隱藏游標（caret-color: transparent）
#   3) input 設 inputmode=none + readonly + autocomplete=off
st.markdown("""
<style>
/* 平板/手機：只隱藏游標（不要改 font-size 或 color，避免 input 失去點擊區） */
@media (hover: none) and (pointer: coarse) {
    [data-testid="stSelectbox"] input,
    [data-testid="stSelectboxVirtual"] input,
    [data-testid="stMultiSelect"] input {
        caret-color: transparent !important;
        -webkit-user-select: none !important;
        user-select: none !important;
    }
}
/* 任何裝置：隱藏游標 */
[data-testid="stSelectbox"] input,
[data-testid="stSelectboxVirtual"] input,
[data-testid="stMultiSelect"] input {
    caret-color: transparent !important;
}
</style>
""", unsafe_allow_html=True)

# === 注入浮動漢堡按鈕（用 components.html 確保 JS 一定會跑） ===
# 功能：
# 1. FAB 永遠顯示在左上角，sidebar 開啟時顯示 X（關閉），收合時顯示（開啟）
# 2. 點 FAB 切換 sidebar
# 3. 點主內容區（不含 sidebar 與 FAB）時，若 sidebar 是開啟的就收合它
# 4. 用 MutationObserver 持續監聽 DOM，確保 FAB 不會被 streamlit 重新渲染清掉
components.html(
    """
<script>
(function() {
    // === 鍵盤抑制器（防止 selectbox 在平板上彈出虛擬鍵盤）===
    // 完整解法：自製 dropdown 完全接管 React Aria 的 listbox
    //
    // 流程：
    //   1) 用戶點 selectbox 容器 → React Aria render listbox
    //   2) MutationObserver 偵測 listbox 進入 DOM
    //   3) 立即「搬移」options 到自製浮動 div
    //   4) 用 CSS 把 React Aria 的 listbox 隱藏到 (-9999, -9999)
    //   5) 用戶點自製 dropdown 的 option → 程式 click 對應 React Aria option → React Aria 處理選中
    //   6) 自製 dropdown 點外面 → close
    //
    // === 鍵盤抑制器（防止 selectbox 在平板上彈出虛擬鍵盤）===
    // 簡化策略：
    //   1) input 收到 focus 後 0ms blur → 防止 iPad 彈虛擬鍵盤（保留 React Aria focus event）
    //   2) 自製 dropdown 蓋在 RAC listbox 上，點自製選項 → 程式 click RAC option → RAC onChange 觸發
    //   3) 自製 dropdown 顯示時，攔截 document mousedown → RAC 不會 close
    //   4) RAC listbox 真正 close（用戶按 ESC 等）時 → 同步移除自製 dropdown
    function setupKeyboardSuppressor() {
        if (window._kbdSuppressInstalled) {
            return;
        }
        window._kbdSuppressInstalled = true;
        var doc = window.parent.document;

        // 1) 不 blur input（避免 RAC 來不及開 dropdown）
        //    改用 CSS 隱藏游標 + 設 inputmode=none
        //    iPad 在 inputmode=none + readonly 時不會彈虛擬鍵盤

        // 2) 自製 dropdown：接收 user click → 程式 click RAC option
        function buildCustomDropdown(listbox) {
            if (doc.getElementById('mobile-custom-dropdown')) return;
            var options = [];
            listbox.querySelectorAll('[role="option"]').forEach(function(o) {
                options.push({text: o.textContent.trim()});
            });
            if (options.length === 0) return;
            // 關鍵：把 RAC listbox + 所有 descendant 設 pointer-events: none
            // 這樣 self dropdown 才能完全接管點擊
            // 但要保留 RAC listbox 自身仍可被 React 更新（不要 unrender）
            // 用 visibility: hidden + pointer-events: none 比較安全
            function setPE(el, val) {
                if (el && el.style) el.style.pointerEvents = val;
                if (el && el.children) {
                    for (var i = 0; i < el.children.length; i++) {
                        setPE(el.children[i], val);
                    }
                }
            }
            // 從 listbox 開始，所有 descendant 設 pointer-events: none
            setPE(listbox, 'none');
            // RAC listbox 透過 portal 渲染，closest 找不到 selectbox
            // 用 aria-controls 反查 combobox，再找 selectbox
            var comboboxId = listbox.getAttribute('aria-labelledby') || '';
            // 直接找 aria-expanded=true 的 input
            var inputs = doc.querySelectorAll('input[aria-expanded="true"]');
            var sb = null;
            if (inputs.length > 0) {
                sb = inputs[0].closest('[data-testid="stSelectbox"], [data-testid="stSelectboxVirtual"], [data-testid="stMultiSelect"]');
            }
            if (!sb) {
                // fallback：找最後 focus 的 selectbox
                sb = doc.activeElement && doc.activeElement.closest &&
                    doc.activeElement.closest('[data-testid="stSelectbox"], [data-testid="stSelectboxVirtual"], [data-testid="stMultiSelect"]');
            }
            if (!sb) {
                // 最後：找第一個 selectbox
                sb = doc.querySelector('[data-testid="stSelectbox"], [data-testid="stSelectboxVirtual"], [data-testid="stMultiSelect"]');
            }
            if (!sb) return;
            var rect = sb.getBoundingClientRect();
            var dd = doc.createElement('div');
            dd.id = 'mobile-custom-dropdown';
            dd.style.cssText = [
                'position: fixed',
                'top: ' + (rect.bottom + 4) + 'px',
                'left: ' + rect.left + 'px',
                'min-width: ' + Math.max(rect.width, 200) + 'px',
                'max-width: 90vw',
                'max-height: 60vh',
                'overflow-y: auto',
                'background: white',
                'border: 1px solid #d0d0d0',
                'border-radius: 10px',
                'box-shadow: 0 8px 24px rgba(0,0,0,0.18)',
                'z-index: 999999',
                'padding: 6px 0',
                '-webkit-overflow-scrolling: touch',
                'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            ].join(';');
            options.forEach(function(opt) {
                var li = doc.createElement('div');
                li.textContent = opt.text;
                li.style.cssText = [
                    'padding: 12px 16px',
                    'cursor: pointer',
                    'font-size: 15px',
                    'line-height: 1.4',
                    'color: #1a1a1a',
                    'background: white',
                    'border-bottom: 1px solid #f0f0f0',
                    'user-select: none',
                    '-webkit-tap-highlight-color: rgba(0,0,0,0.05)',
                ].join(';');
                function pickOption(e) {
                    console.log('[sel] pickOption called for', opt.text, 'event type:', e && e.type);
                    if (e) { e.preventDefault(); e.stopPropagation(); }
                    // 找到當前 DOM 對應的 RAC option
                    var racOpts = doc.querySelectorAll('[role="listbox"] [role="option"]');
                    var target = null;
                    for (var i = 0; i < racOpts.length; i++) {
                        if (racOpts[i].textContent.trim() === opt.text) {
                            target = racOpts[i];
                            break;
                        }
                    }
                    console.log('[sel] target:', target ? target.textContent.trim() : 'null', 'data-key:', target && target.getAttribute('data-key'));
                    if (target) {
                        try {
                            var origPE = target.style.pointerEvents;
                            target.style.pointerEvents = 'auto';
                            var opts = { bubbles: true, cancelable: true, composed: true, view: window, button: 0 };
                            console.log('[sel] dispatching events');
                            target.dispatchEvent(new PointerEvent('pointerdown', Object.assign({}, opts, { pointerType: 'mouse', isPrimary: true, pointerId: 1, buttons: 1 })));
                            target.dispatchEvent(new PointerEvent('pointerup', Object.assign({}, opts, { pointerType: 'mouse', isPrimary: true, pointerId: 1, buttons: 0 })));
                            target.dispatchEvent(new MouseEvent('click', Object.assign({}, opts, { detail: 1 })));
                            console.log('[sel] dispatched all events');
                            setTimeout(function() {
                                target.style.pointerEvents = origPE;
                            }, 200);
                        } catch (err) {
                            console.error('[sel] err:', err);
                        }
                    } else {
                        // RAC options 已被重新 render → 用 text 找新 element
                        console.warn('[sel] retry: looking for new RAC option');
                        setTimeout(function() {
                            var racOpts2 = doc.querySelectorAll('[role="listbox"] [role="option"]');
                            var target2 = null;
                            for (var j = 0; j < racOpts2.length; j++) {
                                if (racOpts2[j].textContent.trim() === opt.text) {
                                    target2 = racOpts2[j];
                                    break;
                                }
                            }
                            if (target2) {
                                console.log('[sel] retry found');
                                target2.style.pointerEvents = 'auto';
                                var opts2 = { bubbles: true, cancelable: true, composed: true, view: window, button: 0 };
                                target2.dispatchEvent(new PointerEvent('pointerdown', Object.assign({}, opts2, { pointerType: 'mouse', isPrimary: true, pointerId: 1, buttons: 1 })));
                                target2.dispatchEvent(new PointerEvent('pointerup', Object.assign({}, opts2, { pointerType: 'mouse', isPrimary: true, pointerId: 1, buttons: 0 })));
                                target2.dispatchEvent(new MouseEvent('click', Object.assign({}, opts2, { detail: 1 })));
                            }
                        }, 50);
                    }
                    setTimeout(function() {
                        var d = doc.getElementById('mobile-custom-dropdown');
                        if (d) d.remove();
                    }, 500);
                }
                li.addEventListener('click', function(e) { console.log('[sel] li click'); pickOption(e); });
                li.addEventListener('touchend', function(e) {
                    if (e) e.preventDefault();
                    console.log('[sel] li touchend');
                    pickOption(e);
                });
                dd.appendChild(li);
            });
            doc.body.appendChild(dd);
        }

        // 3) 攔截 document mousedown/touchstart 在自製 dropdown 內 → RAC 視為「點選項而非外點擊」
        doc.addEventListener('mousedown', function(e) {
            if (e.target.closest && e.target.closest('#mobile-custom-dropdown')) {
                e.stopPropagation();
            }
        }, true);
        doc.addEventListener('touchstart', function(e) {
            if (e.target.closest && e.target.closest('#mobile-custom-dropdown')) {
                e.stopPropagation();
            }
        }, true);

        // 4) 偵測 RAC listbox 出現 → 建立自製 dropdown
        var openObs = new MutationObserver(function(mutations) {
            for (var i = 0; i < mutations.length; i++) {
                var added = mutations[i].addedNodes;
                for (var j = 0; j < added.length; j++) {
                    var n = added[j];
                    if (n.nodeType !== 1) continue;
                    var lb = null;
                    if (n.getAttribute && n.getAttribute('role') === 'listbox') {
                        lb = n;
                    } else if (n.querySelectorAll) {
                        var found = n.querySelector('[role="listbox"]');
                        if (found && found.querySelectorAll('[role="option"]').length > 0) {
                            lb = found;
                        }
                    }
                    if (lb) {
                        console.log('[sel] listbox detected');
                        setTimeout(function() { buildCustomDropdown(lb); }, 50);
                        return;
                    }
                }
            }
        });
        openObs.observe(doc.body, { childList: true, subtree: true });

        // 5) 偵測 RAC listbox 消失 → 移除自製 dropdown
        var closeObs = new MutationObserver(function(mutations) {
            for (var i = 0; i < mutations.length; i++) {
                var removed = mutations[i].removedNodes;
                for (var j = 0; j < removed.length; j++) {
                    var n = removed[j];
                    if (n.nodeType !== 1) continue;
                    if (n.getAttribute && n.getAttribute('role') === 'listbox') {
                        var d = doc.getElementById('mobile-custom-dropdown');
                        if (d) d.remove();
                    }
                }
            }
        });
        closeObs.observe(doc.body, { childList: true, subtree: true });

        // 2) 設 input 屬性：inputmode=none + autocomplete=off + readonly
        //    延遲到 100ms 後，避免干擾 React Aria 初始化
        function patchInputs() {
            var sel = doc.querySelectorAll(
                '[data-testid="stSelectbox"] input, ' +
                '[data-testid="stSelectboxVirtual"] input, ' +
                '[data-testid="stMultiSelect"] input'
            );
            for (var i = 0; i < sel.length; i++) {
                var el = sel[i];
                if (!el.hasAttribute('inputmode')) el.setAttribute('inputmode', 'none');
                if (!el.hasAttribute('autocomplete')) el.setAttribute('autocomplete', 'off');
                if (!el.hasAttribute('readonly')) el.setAttribute('readonly', '');
            }
        }
        setTimeout(patchInputs, 200);
        setTimeout(patchInputs, 1000);
    }
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
    // === 啟動 ===
    setupMainClickHandler();
    setupKeyboardSuppressor();

    // 多重 retry 確保一定注入
    if (!tryInject()) {
        setTimeout(tryInject, 200);
        setTimeout(tryInject, 500);
        setTimeout(tryInject, 1000);
        setTimeout(tryInject, 2000);
        setTimeout(tryInject, 4000);
    }
    // 等 sidebar 出來後啟動 observer


})();
</script>
""",
    height=0,
    width=0,
)



# === 側邊欄 ===
# v10 改進：分區塊折疊收納，減少視覺壓迫感
# 區塊 1：交易所與基本設定（預設展開）
# 區塊 2：回測時間與數據（預設展開）
# 區塊 3：策略核心參數（預設展開）
# 進階（策略管理、BingX 熱門）內嵌 expander 折疊
with st.sidebar:
    # === 區塊 1：交易所與基本設定 ===
    with st.expander(" 交易所與基本設定", expanded=True):
        data_source = st.radio(
            "選擇資料來源",
            ["加密貨幣 (CCXT)", "上傳 CSV", "配對交易 (Pair)"],
            index=0,
            help="選擇要回測的標的類型（加密貨幣即時抓取 / CSV 上傳 / 配對交易）",
        )
        is_pair_trading = (data_source == "配對交易 (Pair)")

        if data_source == "加密貨幣 (CCXT)":
            exchange_ids = get_available_exchanges()
            exchange_labels = {eid: get_exchange_display_name(eid) for eid in exchange_ids}
            default_idx = exchange_ids.index("bingx") if "bingx" in exchange_ids else 0
            selected_exchange = st.selectbox(
                "交易所",
                exchange_ids,
                index=default_idx,
                format_func=lambda x: f"{exchange_labels.get(x, x)}  ({x})",
                help="選擇要抓取資料的交易所",
            )
            default_sym = get_default_symbol(selected_exchange)
            symbol = st.text_input(
                "交易對",
                value=default_sym,
                key="symbol_input",
                placeholder="例如: BTC/USDT",
                help="輸入想回測的交易對代號，格式: 基礎幣/報價幣（如 BTC/USDT）",
            )

            if selected_exchange == "bingx":
                popular = get_bingx_popular_symbols()
                with st.expander(" BingX 熱門交易對（快速填入）", expanded=False):
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

        elif data_source == "上傳 CSV":
            uploaded = st.file_uploader(
                "上傳 CSV 檔案",
                type=["csv"],
                help="CSV 需含欄位: open, high, low, close（volume 選填）",
            )
            if uploaded is not None:
                try:
                    df = load_csv_data(uploaded)
                    if df is not None and not df.empty:
                        st.session_state["df"] = df
                        st.session_state["is_pair"] = False
                        st.session_state["current_step"] = 1
                        st.success(f" 載入 {len(df):,} 筆資料")
                        st.rerun()
                except Exception as e:
                    st.error(f" {e}")

        elif data_source == "配對交易 (Pair)":
            st.caption("配對交易：同時下兩個反向部位")
            pair_templates = get_pair_templates()
            pair_labels = {p["name"]: p for p in pair_templates}
            selected_pair_name = st.selectbox(
                "選擇配對組合",
                list(pair_labels.keys()),
                index=0,
                help="選擇內建的配對交易組合（如 BTC/ETH 比率）",
            )
            selected_pair = pair_labels[selected_pair_name]
            st.caption(f" {selected_pair['symbol1']} vs {selected_pair['symbol2']}")

    df = None

    # === 區塊 2：回測時間與數據 ===
    with st.expander(" 回測時間與數據", expanded=True):
        if data_source == "加密貨幣 (CCXT)":
            timeframe = st.selectbox(
                "時間框架",
                get_timeframes(),
                index=4,
                key="timeframe_input",
                help="K 線週期：1m, 5m, 15m, 1h, 4h, 1d, 1w 等",
            )
            days = st.number_input(
                "回看天數",
                min_value=7,
                max_value=1825,
                value=180,
                step=7,
                key="days_input",
                help="回測歷史資料的天數（最少 7 天，最多 5 年）",
            )
        elif data_source == "配對交易 (Pair)":
            pc1, pc2 = st.columns(2, gap="small")
            with pc1:
                pair_exchange = st.selectbox(
                    "交易所",
                    get_available_exchanges(),
                    index=0,
                    format_func=lambda x: f"{get_exchange_display_name(x)} ({x})",
                    key="pair_exchange",
                    help="配對標的使用的交易所",
                )
            with pc2:
                pair_timeframe = st.selectbox(
                    "時間框架",
                    get_timeframes(),
                    index=4,
                    key="pair_timeframe",
                    help="配對標的的 K 線週期",
                )
            pair_days = st.number_input(
                "回看天數",
                min_value=7,
                max_value=1825,
                value=30,
                step=7,
                key="pair_days",
                help="配對回測歷史天數（最少 7 天，最多 5 年）",
            )

    # === 核心動作按鈕：放最顯眼處（不藏在 expander 內）===
    if data_source == "加密貨幣 (CCXT)":
        if st.button(" 抓取資料", type="primary", use_container_width=True,
                     help=f"從 {get_exchange_display_name(selected_exchange)} 抓取 {symbol} 的 {timeframe} K 線"):
            with st.spinner(f"正在從 {get_exchange_display_name(selected_exchange)} 抓取 {symbol} 資料..."):
                try:
                    df = fetch_crypto_data(symbol, timeframe, days, selected_exchange)
                    if df is not None and not df.empty:
                        st.session_state["df"] = df
                        st.session_state["exchange"] = selected_exchange
                        st.session_state["symbol"] = symbol
                        st.session_state["timeframe"] = timeframe
                        st.session_state["is_pair"] = False
                        st.session_state["current_step"] = 1
                        st.success(f" 從 {get_exchange_display_name(selected_exchange)} 抓取 {len(df):,} 根 K 線")
                        st.rerun()
                    else:
                        st.error(" 抓取失敗：無資料")
                except ValueError as e:
                    st.error(f" 參數錯誤: {e}")
                except ConnectionError as e:
                    st.error(f" 連線問題: {e}")
                except RuntimeError as e:
                    st.error(f" 交易所錯誤: {e}")
                except Exception as e:
                    st.error(f" 未預期錯誤 ({type(e).__name__}): {e}")

        if st.button("一鍵測試資料", use_container_width=True,
                     help="根據目前 timeframe 與回看天數生成模擬 K 線，無需網路"):
            try:
                np.random.seed(42)
                # 根據 UI 選擇的 timeframe 動態計算 K 線數量
                tf_hours_map = {
                    "1m": 1/60, "5m": 5/60, "15m": 0.25, "30m": 0.5,
                    "1h": 1, "2h": 2, "4h": 4, "6h": 6, "12h": 12,
                    "1d": 24, "1w": 168,
                }
                freq_map = {
                    "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
                    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "12h": "12h",
                    "1d": "1D", "1w": "1W",
                }
                hours_per_bar = tf_hours_map.get(timeframe, 1)
                freq_str = freq_map.get(timeframe, "1h")
                n = max(100, int(days * 24 / hours_per_bar))
                n = min(n, 50000)  # 上限保護

                # 真實加密貨幣波動率：年化 70%
                bars_per_year = 365 * 24 / hours_per_bar
                bar_vol = 0.70 / (bars_per_year ** 0.5)

                base_price = 30000
                returns = np.random.normal(0.0001, bar_vol, n)
                close = base_price * np.exp(np.cumsum(returns))
                intrabar = np.abs(np.random.normal(0, bar_vol * 0.3, n))
                high = close * (1 + intrabar)
                low = close * (1 - intrabar)
                open_ = np.roll(close, 1)
                open_[0] = base_price
                volume = np.random.uniform(100, 1000, n)
                test_df = pd.DataFrame({
                    "open": open_, "high": high, "low": low, "close": close, "volume": volume,
                }, index=pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=n, freq=freq_str))
                st.session_state["df"] = test_df
                st.session_state["is_pair"] = False
                st.session_state["symbol"] = "TEST/USDT"
                st.session_state["exchange"] = "synthetic"
                st.session_state["timeframe"] = timeframe
                st.session_state.pop("pair_info", None)
                st.session_state["current_step"] = 1
                dt_start = test_df.index[0].strftime("%Y-%m-%d")
                dt_end = test_df.index[-1].strftime("%Y-%m-%d")
                st.success(f"已生成 {len(test_df):,} 根 {timeframe} K 線（{dt_start} → {dt_end}，${close[0]:,.0f} → ${close[-1]:,.0f}）")
                st.rerun()
            except Exception as e:
                st.error(f"生成測試資料失敗: {e}")

    elif data_source == "配對交易 (Pair)":
        if st.button(" 抓取配對資料", type="primary", use_container_width=True,
                     help=f"抓取 {selected_pair['symbol1']} + {selected_pair['symbol2']} 配對資料"):
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
                        st.session_state["current_step"] = 1
                        st.success(f" 抓取 {len(pair_df):,} 根配對 K 線")
                        st.rerun()
                    else:
                        st.error(" 抓取失敗")
                except Exception as e:
                    st.error(f" {e}")

    # === 載入狀態顯示（如果有資料） ===
    if "df" in st.session_state and df is None:
        df = st.session_state["df"]
        is_pair = st.session_state.get("is_pair", False)
        if is_pair:
            pair_info = st.session_state.get("pair_info", {})
            st.success(f" 配對：{pair_info.get('symbol1', '?')} + {pair_info.get('symbol2', '?')} ({len(df):,} 根)")
        else:
            st.success(f" 已載入快取資料：{len(df):,} 根 K 線")
        if st.button(" 清除資料", use_container_width=True, help="清除目前載入的資料並重置步進器"):
            del st.session_state["df"]
            st.session_state["is_pair"] = False
            st.session_state.pop("pair_info", None)
            st.session_state["current_step"] = 0
            st.rerun()

    if df is not None and not df.empty:
        data_info = f"{len(df):,} 根 K 線 | {df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d')}"
        st.caption(data_info)

    # === 進階：策略管理（折疊收納，預設關閉）===
    with st.expander("策略管理（進階）", expanded=True):
        st.caption("管理自訂策略：上傳 .py / 貼上代碼 / 載入社群範本")

        if "user_strategies" not in st.session_state:
            st.session_state["user_strategies"] = {}

        st.markdown("**① 上傳 .py 檔案**")
        uploaded_files = st.file_uploader(
            "選擇 .py 檔（可多選）",
            type=["py"],
            accept_multiple_files=True,
            key="strategy_uploader",
            help="上傳自訂策略的 Python 檔案",
        )
        if uploaded_files:
            for f in uploaded_files:
                if f.name in st.session_state["user_strategies"]:
                    continue
                success, result, fname = load_strategy_from_file(f)
                if success:
                    name = extract_strategy_name(result, fallback=fname)
                    st.session_state["user_strategies"][fname] = result
                    st.success(f" 已載入: **{name}** ({fname})")
                else:
                    st.error(result)

        st.markdown("**② 貼上 Python 代碼**")
        pasted_code = st.text_area(
            "貼上策略代碼",
            height=120,
            key="pasted_strategy",
            placeholder="def generate_signals(df, params):\n    ...",
            help="貼上策略的 Python 代碼（需含 generate_signals 函數）",
        )
        pasted_name = st.text_input(
            "策略名稱",
            value="我的策略",
            key="pasted_name",
            placeholder="給這個策略取個名字",
            help="策略在策略庫中顯示的名稱",
        )
        if st.button(" 加入到策略庫", use_container_width=True, key="add_pasted_strategy",
                     help="將貼上的代碼加入「我的策略庫」"):
            if not pasted_code.strip():
                st.error("請貼上代碼")
            else:
                success, result = load_strategy_from_pasted_code(pasted_code)
                if success:
                    final_name = pasted_name.strip() or extract_strategy_name(pasted_code)
                    st.session_state["user_strategies"][final_name] = result
                    st.success(f" 已加入: **{final_name}**")
                    st.rerun()
                else:
                    st.error(result)

        st.markdown("**③ 一鍵載入社群策略範本**")
        st.caption("內建 4 個進階策略範本")
        sample_cols = st.columns(2)
        sample_names = list(SAMPLE_STRATEGIES.keys())
        for i, sname in enumerate(sample_names):
            with sample_cols[i % 2]:
                if sname not in st.session_state["user_strategies"]:
                    if st.button(f" {sname}", key=f"add_sample_{i}",
                                  use_container_width=True,
                                  help=f"載入「{sname}」範本到策略庫"):
                        st.session_state["user_strategies"][sname] = SAMPLE_STRATEGIES[sname]
                        st.success(f" 已加入: {sname}")
                        st.rerun()
                else:
                    st.button(f" {sname}", key=f"has_sample_{i}",
                              disabled=True, use_container_width=True,
                              help="已在策略庫中")

        if st.session_state["user_strategies"]:
            st.markdown("** 我的策略庫**")
            for sname in list(st.session_state["user_strategies"].keys()):
                col_s1, col_s2 = st.columns([4, 1])
                with col_s1:
                    st.caption(f"• {sname}")
                with col_s2:
                    if st.button("刪除", key=f"del_{sname}", help=f"刪除 {sname}"):
                        del st.session_state["user_strategies"][sname]
                        st.rerun()

    st.divider()

    # === 區塊 3：策略核心參數（回測設定） ===
    with st.expander(" 策略核心參數（回測設定）", expanded=True):
        initial_capital = st.number_input(
            "初始資金 (USDT)",
            min_value=100.0,
            max_value=10_000_000.0,
            value=10000.0,
            step=1000.0,
            help="回測起始資金（最少 100，最多 1,000 萬 USDT）",
        )
        fee_col1, fee_col2 = st.columns(2, gap="small")
        with fee_col1:
            commission_pct = st.number_input(
                "手續費 (%)",
                min_value=0.0,
                max_value=5.0,
                value=0.1,
                step=0.05,
                help="每筆交易的單邊手續費率（0-5%）",
            ) / 100
        with fee_col2:
            slippage_pct = st.number_input(
                "滑點 (%)",
                min_value=0.0,
                max_value=2.0,
                value=0.05,
                step=0.01,
                help="每筆交易的單邊滑點（0-2%）",
            ) / 100

        use_sl_tp = st.checkbox(
            "啟用停損/停利",
            value=False,
            help="勾選後可設定停損（SL）與停利（TP）百分比",
        )
        if use_sl_tp:
            sl_tp_col1, sl_tp_col2 = st.columns(2, gap="small")
            with sl_tp_col1:
                stop_loss = st.number_input(
                    "停損 (%)",
                    min_value=0.1,
                    max_value=50.0,
                    value=2.0,
                    step=0.5,
                    help="觸發停損的虧損百分比（0.1-50%）",
                ) / 100
            with sl_tp_col2:
                take_profit = st.number_input(
                    "停利 (%)",
                    min_value=0.1,
                    max_value=100.0,
                    value=4.0,
                    step=0.5,
                    help="觸發停利的獲利百分比（0.1-100%）",
                ) / 100
        else:
            stop_loss = None
            take_profit = None



# === 主區域：先檢查資料 ===
# v9 改進：用 st.session_state["current_step"] 動態管理步進器
# 載入資料成功後自動前進到下一步（current_step=1）
if df is None or df.empty:
    # 步驟 0/1：仍顯示「快速開始」引導，但步進器跟著 session_state 動態變
    st.markdown(section_header("快速開始", "", current_theme, size="lg"), unsafe_allow_html=True)
    st.markdown(step_indicator(
        ["選擇資料來源", "載入資料", "選擇策略", "執行回測", "檢視結果"],
        current=st.session_state["current_step"],
        theme=current_theme,
    ), unsafe_allow_html=True)
    # 質感化歡迎面板：只在 current_step == 0（完全沒開始）時顯示
    # v9 改進：漸層 hero + 3 步驟引導卡 + 策略範本標籤雲 + 底部提示
    # 一旦進入步驟 1（已載入資料）就自動隱藏，改為渲染策略/回測 UI
    if st.session_state["current_step"] == 0:
        # v10 改進：改用 st.html()（streamlit 1.59+ 推薦方式）
        # 原本用 st.markdown(..., unsafe_allow_html=True) 在某些 streamlit 版本
        # 會把整段 HTML 當純文字輸出（尤其是含 CSS Grid `display: grid` 時）
        # st.html() 內部用 DOMPurify sanitize，可靠性更高
        try:
            st.html(welcome_panel(theme=current_theme))
        except AttributeError:
            # 備援：舊版 streamlit 沒有 st.html
            st.markdown(welcome_panel(theme=current_theme), unsafe_allow_html=True)
    st.stop()


# 取得配對資訊
is_pair = st.session_state.get("is_pair", False)
pair_info = st.session_state.get("pair_info", {})


# === 三大功能分頁 ===
main_tab1, main_tab2, main_tab3 = st.tabs([
    "單次回測",
    "自動參數優化",
    "Walk-Forward 驗證"
])


# ===========================
# 分頁 1：單回目測
# ===========================
with main_tab1:
    # 流程指示器（Impeccable）
    st.markdown(section_header("策略程式碼", "", current_theme, size="lg"), unsafe_allow_html=True)
    st.markdown(step_indicator(
        ["選擇策略", "編輯代碼", "執行回測", "檢視結果"],
        current=1,
        theme=current_theme,
    ), unsafe_allow_html=True)

    col_src1, col_src2 = st.columns([3, 1])
    with col_src1:
        all_sources = ["（自訂）"] + list_templates()
        if st.session_state.get("user_strategies"):
            all_sources += ["── 我的策略庫 ──"] + list(st.session_state["user_strategies"].keys())

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
                # 同步更新策略參數（Row layout 編輯器）
                default_p = get_default_params(template_choice)
                st.session_state["strategy_params_dict"] = default_p.copy()
                st.session_state.pop("strategy_params_params", None)  # 清掉舊 session
                st.rerun()

    with col_src2:
        st.write("")
        if template_choice.startswith("──"):
            st.button("載入", key="load_template", disabled=True, use_container_width=True)
        else:
            if st.button(" 重新載入", key="load_template", use_container_width=True,
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
                    # 同步更新策略參數（Row layout 編輯器）
                    default_p = get_default_params(template_choice)
                    st.session_state["strategy_params_dict"] = default_p.copy()
                    st.session_state.pop("strategy_params_params", None)  # 清掉舊 session
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

    with st.expander("策略參數", expanded=True):
        current_t = st.session_state.get("current_template", "")
        if current_t and current_t != "（自訂）":
            default_params = get_default_params(current_t)
        else:
            default_params = {"period": 20}

        # 確保 session_state["strategy_params_dict"] 與當前策略一致
        # 切換策略時已自動設定
        if "strategy_params_dict" not in st.session_state:
            st.session_state["strategy_params_dict"] = default_params.copy()

        # 用 Row layout 編輯器
        from utils.param_editor import render_param_editor
        strategy_params = render_param_editor(
            label="策略參數",
            current_params=st.session_state["strategy_params_dict"],
            key_prefix="strategy_params",
            caption="以 Row layout 編輯參數：左為名稱，右為值",
        )
        # 同步回 session_state
        st.session_state["strategy_params_dict"] = strategy_params

    st.divider()
    col_btn1, col_btn2 = st.columns([1, 5])
    with col_btn1:
        run_single = st.button(" 執行回測", type="primary", use_container_width=True, key="run_single")
    with col_btn2:
        if st.button(" 儲存策略代碼", use_container_width=False):
            st.session_state["strategy_code"] = strategy_code
            st.success("已儲存")

    # 關鍵：只在按下按鈕時才執行後續，否則「自然結束」這個 tab
    # 方向由 strategy 自動決定（不讓用戶選）：
    # - 如果 strategy 回傳 4 個 series (long_entries, long_exits, short_entries, short_exits)
    #   → 自動用 long_short 模式
    # - 如果 strategy 回傳 2 個 series (entries, exits)
    #   → 預設 long 模式
    # 透過檢查 long_entries/short_entries 是否有訊號來自動選擇
    # v9 改進：藍色提示框只在「從未執行過回測」時顯示
    # 只要 session_state["bt_result_df"] 存在（曾執行過）就完全隱藏
    # 讓回測數據與圖表直接呈現在畫面最上方
    # v10 改進：else 內只在 run_single=True 時執行回測
    # （避免 re-render 時重複跑回測 + 觸發 DuplicateElementKey）
    has_backtest_result = "bt_result_df" in st.session_state and st.session_state.get("bt_result_df") is not None
    if not run_single and not has_backtest_result:
        st.info("點擊「 執行回測」開始分析")
    elif run_single:
        # 執行策略（最外層 try 確保任何錯誤都不會導致整個 app 崩潰）
        try:
            result = execute_user_strategy(strategy_code, df, strategy_params)
            # 顯示 debug 資訊（只顯示長度，不暴露內容）
            result_type = type(result).__name__
            result_len = len(result) if hasattr(result, '__len__') else 'N/A'
            # 防護：確保 result 是 7-tuple
            if not isinstance(result, tuple) or len(result) != 7:
                st.warning(f" 策略回傳了 {result_len} 個元素（type={result_type}），自動補齊為 7 個")
                empty_series = pd.Series(False, index=df.index)
                result_list = list(result) if isinstance(result, (tuple, list)) else []
                while len(result_list) < 7:
                    result_list.append(empty_series)
                result = tuple(result_list[:7])
            entries, exits, err, long_entries, long_exits, short_entries, short_exits = result
        except Exception as e:
            st.error(f" 策略執行失敗: {type(e).__name__}: {e}")
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
            st.warning(" 策略沒有產生任何進場訊號（long/short 都沒有）")
        elif actual_direction == "long" and not entries.any():
            st.warning(" 策略沒有產生任何進場訊號")
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
                        st.error(f" 配對回測引擎錯誤: {type(e).__name__}: {e}")
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
                        st.error(f" 回測引擎錯誤: {type(e).__name__}: {e}")
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
                # v10 改進：標記已 render overview，避免下方 if 區塊重複執行
                st.session_state["_has_rendered_overview_this_run"] = True
                # 5 分頁結果顯示
                result_tab1, result_tab2, result_tab3, result_tab4, result_tab5 = st.tabs([
                    "總覽",
                    "績效摘要",
                    "交易明細",
                    "圖表",
                    "蒙地卡羅",
                ])

                with result_tab1:
                    render_overview(metrics, result_df, initial_capital, trades=trades)

                with result_tab2:
                    render_performance_summary(trades, metrics)

                with result_tab3:
                    render_list_of_trades(trades)

                with result_tab4:
                    render_charts(result_df, trades)

                with result_tab5:
                    render_monte_carlo(initial_capital, trades)

    # 即使沒按「 執行回測」，若有先前結果 → 顯示結果 tabs
    # v9 改進：藍色提示框只在「從未執行過回測」時顯示
    # 已執行過的話，數據直接呈現，不顯示提示
    # v10 改進：避免重複 render_overview（會觸發 DuplicateElementKey）
    # 用 _has_rendered_overview_this_run 旗標防止 else 與 if 兩處都執行
    _already_rendered = st.session_state.get("_has_rendered_overview_this_run", False)
    if (
        not run_single
        and "bt_result_df" in st.session_state
        and st.session_state.get("bt_trades")
        and not _already_rendered
    ):
        result_df = st.session_state["bt_result_df"]
        trades = st.session_state["bt_trades"]
        metrics = st.session_state["bt_metrics"]

        # 已執行過回測 → 不再顯示「顯示先前的回測結果」提示框
        # 結果 tabs 直接接續渲染，數據呈現在畫面最上方

        result_tab1, result_tab2, result_tab3, result_tab4, result_tab5 = st.tabs([
            "總覽",
            "績效摘要",
            "交易明細",
            "圖表",
            "蒙地卡羅",
        ])

        with result_tab1:
            render_overview(metrics, result_df, initial_capital, trades=trades)

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
    st.markdown(section_header("自動參數優化", "", current_theme, size="lg"), unsafe_allow_html=True)
    st.caption("自動測試所有參數組合，找出最佳表現。支援 Grid Search 與 Bayesian Optimization。")

    col_o1, col_o2 = st.columns([3, 1])
    with col_o1:
        opt_sources = list_templates()
        if st.session_state.get("user_strategies"):
            opt_sources += ["── 我的策略庫 ──"] + list(st.session_state["user_strategies"].keys())
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
                    new_specs = get_default_specs_for_strategy(opt_template)
                elif opt_template in st.session_state.get("user_strategies", {}):
                    new_code = st.session_state["user_strategies"][opt_template]
                    new_space = {}
                    new_default = {}
                    new_specs = []
                else:
                    new_code = None
                if new_code is not None:
                    st.session_state["opt_code"] = new_code
                    st.session_state["opt_param_space"] = new_space
                    st.session_state["opt_default_params"] = new_default
                    st.session_state["opt_param_specs"] = new_specs
                    st.session_state["opt_current"] = opt_template
                    # 同步更新 widget state
                    st.session_state["opt_code_editor"] = new_code
                    # 同步更新 Row layout 編輯器（清掉舊 session）
                    st.session_state.pop("opt_fixed_params_params", None)
                    st.session_state.pop("opt_param_space_params", None)
                    st.session_state.pop("opt_param_space_storage", None)
                    st.rerun()

    with col_o2:
        st.write("")
        st.write("")
        if opt_template.startswith("──"):
            st.button("載入", key="load_opt_template", disabled=True, use_container_width=True)
        else:
            if st.button(" 重新載入", key="load_opt_template", use_container_width=True,
                         help="重新從範本載入（會覆蓋目前編輯的代碼）"):
                if opt_template in list_templates():
                    new_code = get_template(opt_template)
                    new_space = get_param_space(opt_template)
                    new_default = get_default_params(opt_template)
                    new_specs = get_default_specs_for_strategy(opt_template)
                elif opt_template in st.session_state.get("user_strategies", {}):
                    new_code = st.session_state["user_strategies"][opt_template]
                    new_space = {}
                    new_default = {}
                    new_specs = []
                else:
                    new_code = None
                if new_code is not None:
                    st.session_state["opt_code"] = new_code
                    st.session_state["opt_param_space"] = new_space
                    st.session_state["opt_default_params"] = new_default
                    st.session_state["opt_param_specs"] = new_specs
                    st.session_state["opt_current"] = opt_template
                    st.session_state["opt_code_editor"] = new_code
                    # 同步更新 Row layout 編輯器（清掉舊 session）
                    st.session_state.pop("opt_fixed_params_params", None)
                    st.session_state.pop("opt_param_space_params", None)
                    st.session_state.pop("opt_param_space_storage", None)
                    st.rerun()

    if "opt_code" not in st.session_state:
        st.session_state["opt_code"] = get_template(list_templates()[0])
        st.session_state["opt_current"] = list_templates()[0]
        st.session_state["opt_param_space"] = get_param_space(list_templates()[0])
        st.session_state["opt_default_params"] = get_default_params(list_templates()[0])
        st.session_state["opt_param_specs"] = get_default_specs_for_strategy(list_templates()[0])

    opt_code = st.text_area("策略代碼（可編輯）", value=st.session_state["opt_code"],
                              height=200, key="opt_code_editor")

    # === 可見性（放在外面，label + widget 並排格式）===
    st.markdown(section_header("可見性", "", current_theme, size="md"), unsafe_allow_html=True)

    vis_left, vis_right = st.columns([1, 3])
    with vis_left:
        st.markdown("<div style='padding-top: 12px; padding-right: 8px; text-align: right;'>優化模式</div>", unsafe_allow_html=True)
    with vis_right:
        opt_mode = st.radio(
            "優化模式",
            ["Bayesian (Optuna)", "Grid Search", "Random Search"],
            key="opt_mode",
            label_visibility="collapsed",
            horizontal=True,
        )
    mode_code = "bayesian" if "Bayesian" in opt_mode else ("grid" if "Grid" in opt_mode else "random")

    vis_left2, vis_right2 = st.columns([1, 3])
    with vis_left2:
        st.markdown("<div style='padding-top: 12px; padding-right: 8px; text-align: right;'>優化目標</div>", unsafe_allow_html=True)
    with vis_right2:
        opt_objective = st.selectbox(
            "優化目標",
            list_objectives(),
            index=list_objectives().index("sharpe_ratio"),
            key="opt_objective",
            label_visibility="collapsed",
            help="目標函數（越高越好）",
        )

    # Bayesian 與 Random 需要 n_trials
    if mode_code in ("bayesian", "random"):
        vis_left3, vis_right3 = st.columns([1, 3])
        with vis_left3:
            st.markdown("<div style='padding-top: 12px; padding-right: 8px; text-align: right;'>迭代次數</div>", unsafe_allow_html=True)
        with vis_right3:
            n_trials = st.number_input(
                "迭代次數 (n_trials)",
                min_value=5, max_value=2000, value=50,
                key="opt_n_trials",
                label_visibility="collapsed",
                help="Bayesian 用 TPE 採樣；Random 用均勻採樣",
            )
        vis_left4, vis_right4 = st.columns([1, 3])
        with vis_left4:
            st.markdown("<div style='padding-top: 12px; padding-right: 8px; text-align: right;'>隨機種子</div>", unsafe_allow_html=True)
        with vis_right4:
            opt_seed = st.number_input(
                "隨機種子 (確保可重現)",
                min_value=0, max_value=999999, value=42,
                key="opt_seed",
                label_visibility="collapsed",
            )

    st.divider()

    # === 兩個 tab：輸入（固定參數）/ 模式（參數空間）===
    tab_input, tab_mode = st.tabs(["輸入", "模式"])

    with tab_input:
        st.caption("固定參數（所有測試都會使用）。可新增/刪除列。")
        from utils.param_editor import render_param_editor
        fixed_params = render_param_editor(
            label="固定參數",
            current_params=st.session_state.get("opt_default_params", {}),
            key_prefix="opt_fixed_params",
            caption=None,
        )

    with tab_mode:
        if mode_code == "bayesian":
            # Bayesian 模式：範圍型參數編輯器
            st.caption("**Bayesian 模式**：每個參數 = 名稱 + 型態 + 範圍。支援 int / float / float_log / categorical")
            param_specs = render_param_space_editor(
                label="參數空間（範圍型）",
                current_specs=st.session_state.get("opt_param_specs", []),
                key_prefix="opt_param_space",
                caption=None,
            )
            # 動態計算「總可能組合數」（用於估算）
            if param_specs:
                from math import prod
                total_est = 1
                for spec in param_specs:
                    ptype = spec.get("type", "int")
                    if ptype in ("int",):
                        low, high = spec.get("low", 1), spec.get("high", 100)
                        total_est *= max(1, (high - low) + 1)
                    elif ptype in ("float", "float_log", "loguniform"):
                        total_est *= 100  # 浮點當 100 級
                    elif ptype == "categorical":
                        total_est *= max(1, len(spec.get("choices", [])))
                col_m1, col_m2, col_m3 = st.columns(3)
                with col_m1:
                    st.metric("搜尋空間（估）", f"~{total_est:,}")
                with col_m2:
                    st.metric("要測試", f"{n_trials}")
                with col_m3:
                    reduction = max(0, 100 - (n_trials / total_est * 100)) if total_est > 0 else 0
                    st.metric("搜尋效率", f"{reduction:.0f}%")
        else:
            # Grid / Random 模式：候選值清單型
            st.caption("**Grid / Random 模式**：每個 key 是參數名，value 是候選值清單（如 [10, 20, 30]）")
            from utils.param_editor import render_param_editor
            param_space = render_param_editor(
                label="參數空間",
                current_params=st.session_state.get("opt_param_space", {}),
                key_prefix="opt_param_space",
                caption=None,
            )
            if mode_code == "grid" and isinstance(param_space, dict) and param_space:
                _total = 1
                for v in param_space.values():
                    if isinstance(v, list):
                        _total *= len(v)
                    else:
                        _total *= 1
                st.metric("組合總數", f"{_total:,}")

    run_opt = st.button("開始優化", type="primary", use_container_width=True)

    if not run_opt:
        st.info("設定參數空間後點擊「開始優化」")
    else:
        # === 統一檢查 ===
        if mode_code == "bayesian":
            if not param_specs:
                st.error("請設定至少一個要優化的參數（範圍型）")
                st.stop()
        else:
            if not param_space:
                st.error("請設定至少一個要優化的參數")
                st.stop()

        # 初始化容器
        progress_bar = st.progress(0)
        status_text = st.empty()
        best_metric_placeholder = st.empty()
        best_value_so_far = -np.inf
        result = None

        try:
            # 自動判斷交易方向：策略有 short 訊號 → long_short，否則 long
            _r = execute_user_strategy(opt_code, df, fixed_params)
            if isinstance(_r, tuple) and len(_r) == 7:
                _, _, _, _le, _, _se, _ = _r
                direction_code = "long_short" if (_se is not None and _se.any()) else "long"
            else:
                direction_code = "long"

            if mode_code == "bayesian":
                status_text.text(f"開始 Bayesian Optimization（{n_trials} trials）...")
                set_global_seed(int(opt_seed))
                opt_engine = OptunaOptimizer(
                    strategy_runner=execute_user_strategy,
                    backtest_engine_class=BacktestEngine,
                    objective_name=opt_objective,
                    sampler="tpe",
                    pruner="median",
                    seed=int(opt_seed),
                )
                start_time = time.time()
                # 進度回呼：即時更新最佳值
                def _on_progress(trial_num, total, current, best, params):
                    progress_bar.progress(min(trial_num / total, 1.0))
                    best_metric_placeholder.metric("目前最佳", f"{best:.4f}", delta=f"trial {trial_num}/{total}")
                result = opt_engine.run(
                    df=df,
                    strategy_code=opt_code,
                    param_specs=param_specs,
                    base_params=fixed_params,
                    initial_capital=initial_capital,
                    commission=commission_pct,
                    slippage=slippage_pct,
                    direction=direction_code,
                    n_trials=int(n_trials),
                    study_name=f"opt_{int(time.time())}",
                    persist=True,
                    progress_callback=_on_progress,
                )
            elif mode_code == "grid":
                status_text.text(f"⏳ 開始 Grid Search...")
                set_global_seed(42)
                opt_engine = ParameterOptimizer(
                    strategy_runner=execute_user_strategy,
                    backtest_engine_class=BacktestEngine,
                    metric=opt_objective,
                )
                start_time = time.time()
                grid_result = opt_engine.grid_search(
                    df, opt_code, param_space, fixed_params,
                    initial_capital, commission_pct, slippage_pct, direction_code,
                )
                result = {
                    "best_params": grid_result["best_params"],
                    "best_value": grid_result["best_metrics"].get(opt_objective, 0) if grid_result["best_metrics"] else None,
                    "best_metrics": grid_result["best_metrics"],
                    "valid_results": grid_result["valid_results"],
                    "all_results": grid_result["all_results"],
                    "total_combinations": grid_result["total_combinations"],
                    "valid_combinations": grid_result["valid_combinations"],
                    "elapsed_seconds": time.time() - start_time,
                    "n_trials_completed": grid_result["valid_combinations"],
                    "n_trials_total": grid_result["total_combinations"],
                }
                progress_bar.progress(100)
            else:  # random
                status_text.text(f"⏳ 開始 Random Search（{n_trials} iterations）...")
                set_global_seed(42)
                opt_engine = ParameterOptimizer(
                    strategy_runner=execute_user_strategy,
                    backtest_engine_class=BacktestEngine,
                    metric=opt_objective,
                )
                start_time = time.time()
                rand_result = opt_engine.random_search(
                    df, opt_code, param_space, fixed_params,
                    initial_capital, commission_pct, slippage_pct, direction_code,
                    n_iter=int(n_trials),
                )
                result = {
                    "best_params": rand_result["best_params"],
                    "best_value": rand_result["best_metrics"].get(opt_objective, 0) if rand_result["best_metrics"] else None,
                    "best_metrics": rand_result["best_metrics"],
                    "valid_results": rand_result["valid_results"],
                    "all_results": rand_result["all_results"],
                    "total_combinations": rand_result["total_combinations"],
                    "valid_combinations": rand_result["valid_combinations"],
                    "elapsed_seconds": time.time() - start_time,
                    "n_trials_completed": rand_result["valid_combinations"],
                    "n_trials_total": rand_result["total_combinations"],
                }
                progress_bar.progress(100)
        except Exception as e:
            progress_bar.progress(100)
            status_text.text(f" 優化失敗")
            st.error(f" 參數優化錯誤: {type(e).__name__}: {e}")
            st.exception(e)
            st.stop()

        progress_bar.progress(100)
        elapsed = result.get("elapsed_seconds", time.time() - start_time)
        n_complete = result.get("n_trials_completed", 0)
        n_total = result.get("n_trials_total", 0)
        status_text.text(f" 完成！耗時 {elapsed:.1f} 秒，有效 {n_complete}/{n_total}")

        if not result.get("best_params"):
            st.error(" 沒有找到任何有效組合，請放寬參數空間或檢查策略代碼")
        else:
            best = result["best_metrics"]
            st.success(f"找到最佳參數！")

            col_r1, col_r2, col_r3, col_r4, col_r5 = st.columns(5)
            with col_r1:
                st.metric("目標值", f"{result.get('best_value', 0):.4f}")
            with col_r2:
                st.metric("最佳 Sharpe", f"{best.get('sharpe_ratio', 0):.2f}")
            with col_r3:
                st.metric("最佳報酬率", f"{best.get('total_return_pct', 0):+.2f}%")
            with col_r4:
                st.metric("最大回撤", f"{best.get('max_drawdown_pct', 0):.2f}%")
            with col_r5:
                st.metric("勝率", f"{best.get('win_rate', 0):.1f}%")

            st.subheader("最佳參數組合")
            st.json(result["best_params"])

            # === 過擬合評估（Grid/Random 模式）===
            if mode_code in ("grid", "random") and result.get("valid_results"):
                st.subheader("過擬合風險評估")
                overfit = calculate_overfit_score(result["valid_results"], top_n=10)
                col_of1, col_of2, col_of3 = st.columns([1, 1, 2])
                with col_of1:
                    st.metric("過擬合評分", f"{overfit['score']:.0f}/100")
                with col_of2:
                    st.metric("參數平原比", f"{overfit.get('avg_ratio', 0):.2f}")
                with col_of3:
                    st.info(overfit["warning"])

            # === 擾動測試（Bayesian 模式）===
            if mode_code == "bayesian" and result.get("best_params"):
                st.subheader("參數穩定性測試（Perturbation Test）")
                with st.spinner("擾動測試中..."):
                    try:
                        from utils.objective_builder import get_objective_fn
                        tester = PerturbationTester(
                            strategy_runner=execute_user_strategy,
                            backtest_engine_class=BacktestEngine,
                            objective_fn=get_objective_fn(opt_objective),
                            objective_name=opt_objective,
                        )
                        perturb_result = tester.run(
                            df=df,
                            strategy_code=opt_code,
                            best_params=result["best_params"],
                            base_params=fixed_params,
                            initial_capital=initial_capital,
                            commission=commission_pct,
                            slippage=slippage_pct,
                        )
                        col_p1, col_p2, col_p3 = st.columns(3)
                        with col_p1:
                            st.metric("穩定度評分", f"{perturb_result['stability_score']:.0f}/100")
                        with col_p2:
                            st.metric("基準目標值", f"{perturb_result['baseline_value']:.4f}")
                        with col_p3:
                            st.metric("擾動後 CV", f"{perturb_result['overall_cv']:.3f}")
                        st.info(perturb_result["interpretation"])
                        with st.expander("查看擾動詳細資料"):
                            st.dataframe(perturb_result["per_param"], use_container_width=True, hide_index=True)
                    except Exception as e:
                        st.warning(f"擾動測試失敗: {e}")

            # === 參數重要性（Bayesian 模式）===
            if mode_code == "bayesian" and result.get("param_importances"):
                st.subheader("參數重要性分析（fANOVA）")
                imp = result["param_importances"]
                if imp:
                    imp_df = pd.DataFrame([
                        {"參數": k, "重要性": float(v)}
                        for k, v in sorted(imp.items(), key=lambda x: -x[1])
                    ])
                    # 文字條形圖
                    fig_imp = go.Figure(go.Bar(
                        x=imp_df["重要性"],
                        y=imp_df["參數"],
                        orientation="h",
                        marker=dict(color=imp_df["重要性"], colorscale="Viridis"),
                    ))
                    fig_imp.update_layout(
                        xaxis_title="重要性",
                        yaxis_title="參數",
                        height=max(200, 50 * len(imp_df)),
                        template="plotly_white",
                        yaxis=dict(autorange="reversed"),
                    )
                    st.plotly_chart(fig_imp, use_container_width=True, config={"staticPlot": True, "displayModeBar": False})

            # === 複製按鈕 ===
            if st.button("複製到單次回測", key="copy_to_single"):
                st.session_state["strategy_code"] = opt_code
                st.session_state["current_template"] = st.session_state.get("opt_current", "")
                merged = {**fixed_params, **result["best_params"]}
                st.session_state["strategy_params_dict"] = merged
                st.session_state.pop("strategy_params_params", None)
                st.success(" 已複製到「單回目測」分頁，請切換查看")

            # === Top 10 結果 ===
            st.subheader(f"Top 10 結果")
            top_display = []
            valid_list = result.get("valid_results", [])
            if not valid_list and "all_trials" in result and not result["all_trials"].empty:
                # 從 DataFrame 提取
                trials_df = result["all_trials"]
                param_cols = [c for c in trials_df.columns if c.startswith("param_")]
                metric_cols = [c for c in trials_df.columns if c.startswith("metric_") or c == "n_trades" or c == "value"]
                trials_sorted = trials_df.sort_values("value", ascending=False).head(10)
                for _, row in trials_sorted.iterrows():
                    item = {c.replace("param_", ""): row[c] for c in param_cols if pd.notna(row[c])}
                    item["目標值"] = row.get("value")
                    item["n_trades"] = row.get("n_trades")
                    top_display.append(item)
            else:
                for r in valid_list[:10]:
                    if isinstance(r, dict):
                        row = {**r.get("params", {})}
                        row["目標值"] = r.get(opt_objective) if opt_objective in r else r.get("value")
                        row["Sharpe"] = r.get("sharpe_ratio", 0)
                        row["報酬率 %"] = r.get("total_return_pct", 0)
                        row["回撤 %"] = r.get("max_drawdown_pct", 0)
                        row["勝率 %"] = r.get("win_rate", 0)
                        row["交易數"] = r.get("n_trades", 0)
                        top_display.append(row)
            if top_display:
                st.dataframe(pd.DataFrame(top_display), use_container_width=True, hide_index=True)

            # === 熱力圖（Grid + 2 個參數）===
            if mode_code == "grid" and isinstance(param_space, dict) and len(param_space) == 2 and valid_list:
                st.subheader("參數熱力圖")
                pname1, pname2 = list(param_space.keys())
                pvals1 = param_space[pname1] if isinstance(param_space[pname1], list) else [param_space[pname1]]
                pvals2 = param_space[pname2] if isinstance(param_space[pname2], list) else [param_space[pname2]]

                heatmap_z = np.full((len(pvals2), len(pvals1)), np.nan)
                for r in valid_list:
                    if not isinstance(r, dict) or "params" not in r:
                        continue
                    v1 = r["params"].get(pname1)
                    v2 = r["params"].get(pname2)
                    if v1 in pvals1 and v2 in pvals2:
                        i = pvals1.index(v1)
                        j = pvals2.index(v2)
                        val = r.get(opt_objective) or r.get(opt_objective.replace("_pct", "_pct"))
                        heatmap_z[j, i] = val

                fig_heat = go.Figure(data=go.Heatmap(
                    z=heatmap_z, x=[str(v) for v in pvals1], y=[str(v) for v in pvals2],
                    colorscale="Viridis",
                    colorbar=dict(title=opt_objective),
                ))
                fig_heat.update_layout(
                    xaxis_title=pname1, yaxis_title=pname2,
                    template="plotly_white", height=500,
                )
                st.plotly_chart(fig_heat, use_container_width=True, config={"staticPlot": True, "displayModeBar": False})

            # === 最佳化歷史圖（Bayesian 模式）===
            if mode_code == "bayesian" and "all_trials" in result and not result["all_trials"].empty:
                trials_df = result["all_trials"]
                trials_df = trials_df[trials_df["value"].notna()].sort_values("number")
                if not trials_df.empty:
                    st.subheader("優化歷史")
                    fig_hist = go.Figure()
                    fig_hist.add_trace(go.Scatter(
                        x=trials_df["number"], y=trials_df["value"],
                        mode="markers", name="Trial 值",
                        marker=dict(size=8, color="lightblue", line=dict(color="blue", width=1)),
                    ))
                    fig_hist.add_trace(go.Scatter(
                        x=trials_df["number"],
                        y=trials_df["value"].cummax(),
                        mode="lines", name="最佳值（累積）",
                        line=dict(color="red", width=2),
                    ))
                    fig_hist.update_layout(
                        xaxis_title="Trial 編號",
                        yaxis_title=opt_objective,
                        template="plotly_white", height=400,
                    )
                    st.plotly_chart(fig_hist, use_container_width=True, config={"staticPlot": True, "displayModeBar": False})


# ===========================
# 分頁 3：Walk-Forward 驗證
# ===========================
with main_tab3:
    st.markdown(section_header("Walk-Forward 驗證", "", current_theme, size="lg"), unsafe_allow_html=True)
    st.caption("""
    將資料切成多個 in-sample（訓練）與 out-of-sample（測試）區段，
    確保策略在「未見過的資料」上也能獲利，避免過擬合。
    """)

    col_w1, col_w2 = st.columns([3, 1])
    with col_w1:
        wf_sources = list_templates()
        if st.session_state.get("user_strategies"):
            wf_sources += ["── 我的策略庫 ──"] + list(st.session_state["user_strategies"].keys())
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
                    new_specs = get_default_specs_for_strategy(wf_template)
                elif wf_template in st.session_state.get("user_strategies", {}):
                    new_code = st.session_state["user_strategies"][wf_template]
                    new_space = {}
                    new_default = {}
                    new_specs = []
                else:
                    new_code = None
                if new_code is not None:
                    st.session_state["wf_code"] = new_code
                    st.session_state["wf_param_space"] = new_space
                    st.session_state["wf_default_params"] = new_default
                    st.session_state["wf_param_specs"] = new_specs
                    st.session_state["wf_current"] = wf_template
                    st.session_state["wf_code_editor"] = new_code
                    # 同步更新 Row layout 編輯器（清掉舊 session）
                    st.session_state.pop("wf_fixed_params_params", None)
                    st.session_state.pop("wf_param_space_params", None)
                    st.session_state.pop("wf_param_space_storage", None)
                    st.rerun()

    with col_w2:
        st.write("")
        st.write("")
        if wf_template.startswith("──"):
            st.button("載入", key="load_wf_template", disabled=True, use_container_width=True)
        else:
            if st.button(" 重新載入", key="load_wf_template", use_container_width=True,
                         help="重新從範本載入（會覆蓋目前編輯的代碼）"):
                if wf_template in list_templates():
                    new_code = get_template(wf_template)
                    new_space = get_param_space(wf_template)
                    new_default = get_default_params(wf_template)
                    new_specs = get_default_specs_for_strategy(wf_template)
                elif wf_template in st.session_state.get("user_strategies", {}):
                    new_code = st.session_state["user_strategies"][wf_template]
                    new_space = {}
                    new_default = {}
                    new_specs = []
                else:
                    new_code = None
                if new_code is not None:
                    st.session_state["wf_code"] = new_code
                    st.session_state["wf_param_space"] = new_space
                    st.session_state["wf_default_params"] = new_default
                    st.session_state["wf_param_specs"] = new_specs
                    st.session_state["wf_current"] = wf_template
                    st.session_state["wf_code_editor"] = new_code
                    # 同步更新 Row layout 編輯器（清掉舊 session）
                    st.session_state.pop("wf_fixed_params_params", None)
                    st.session_state.pop("wf_param_space_params", None)
                    st.session_state.pop("wf_param_space_storage", None)
                    st.rerun()

    if "wf_code" not in st.session_state:
        st.session_state["wf_code"] = get_template(list_templates()[0])
        st.session_state["wf_current"] = list_templates()[0]
        st.session_state["wf_param_space"] = get_param_space(list_templates()[0])
        st.session_state["wf_param_specs"] = get_default_specs_for_strategy(list_templates()[0])

    wf_code = st.text_area("策略代碼", value=st.session_state["wf_code"], height=200, key="wf_code_editor")

    # === 可見性（放在外面，label + widget 並排格式）===
    st.markdown(section_header("可見性", "", current_theme, size="md"), unsafe_allow_html=True)
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
            list_objectives(),
            index=list_objectives().index("sharpe_ratio"),
            key="wf_metric",
            label_visibility="collapsed"
        )

    vis_left5, vis_right5 = st.columns([1, 3])
    with vis_left5:
        st.markdown("<div style='padding-top: 12px; padding-right: 8px; text-align: right;'>內部優化器</div>", unsafe_allow_html=True)
    with vis_right5:
        wf_inner_opt = st.radio(
            "內部優化器",
            ["Optuna (Bayesian)", "Grid Search"],
            key="wf_inner_opt",
            label_visibility="collapsed",
            horizontal=True,
        )
    wf_inner_code = "optuna" if "Optuna" in wf_inner_opt else "grid"

    if wf_inner_code == "optuna":
        vis_left6, vis_right6 = st.columns([1, 3])
        with vis_left6:
            st.markdown("<div style='padding-top: 12px; padding-right: 8px; text-align: right;'>每次 trials</div>", unsafe_allow_html=True)
        with vis_right6:
            wf_inner_trials = st.number_input(
                "每次 fold 內部 trials",
                min_value=5, max_value=200, value=20,
                key="wf_inner_trials",
                label_visibility="collapsed",
                help="每個 WF fold 內部 Optuna 跑的試驗數",
            )

    st.divider()

    # === 兩個 tab：輸入（固定參數）/ 模式（參數空間）===
    wf_tab_input, wf_tab_mode = st.tabs(["輸入", "模式"])

    with wf_tab_input:
        st.caption("固定參數。可新增/刪除列。")
        from utils.param_editor import render_param_editor
        wf_default = st.session_state.get("wf_default_params") or get_default_params(
            st.session_state.get("wf_current", list_templates()[0])
        )
        wf_fixed = render_param_editor(
            label="固定參數",
            current_params=wf_default,
            key_prefix="wf_fixed_params",
            caption=None,
        )

    with wf_tab_mode:
        if wf_inner_code == "optuna":
            st.caption("**Optuna 模式**：每個參數 = 名稱 + 型態 + 範圍")
            wf_param_specs = render_param_space_editor(
                label="參數空間（範圍型）",
                current_specs=st.session_state.get("wf_param_specs", get_default_specs_for_strategy(wf_template)),
                key_prefix="wf_param_space",
                caption=None,
            )
            wf_param_space = None
        else:
            st.caption("**Grid 模式**：每個 key 是參數名，value 是候選值清單（如 [10, 20, 30]）")
            from utils.param_editor import render_param_editor
            wf_param_space = render_param_editor(
                label="參數空間",
                current_params=st.session_state.get("wf_param_space", {}),
                key_prefix="wf_param_space",
                caption=None,
            )
            wf_param_specs = None

    run_wf = st.button("執行 Walk-Forward 驗證", type="primary", use_container_width=True)

    if not run_wf:
        st.info("設定參數後點擊「執行 Walk-Forward 驗證」")
    else:
        # 配對模式設定
        if is_pair and pair_info:
            st.info(f"配對 WF 模式：{pair_info.get('symbol1')} + {pair_info.get('symbol2')}")
            wf_engine = PairBacktestEngine
            wf_pair_kwargs = {
                "symbol1": pair_info.get("symbol1", "BTC/USDT"),
                "symbol2": pair_info.get("symbol2", "ETH/USDT"),
            }
        else:
            wf_engine = BacktestEngine
            wf_pair_kwargs = {}

        # 根據內部優化器決定參數
        if wf_inner_code == "optuna":
            if not wf_param_specs:
                st.error("請先設定至少一個要優化的參數（範圍型）")
                st.stop()
            inner_n_trials = int(wf_inner_trials) if 'wf_inner_trials' in dir() else 20
        else:
            if not wf_param_space:
                st.error("請先設定至少一個要優化的參數")
                st.stop()
            inner_n_trials = 0  # grid 不需要

        validator = WalkForwardValidator(
            strategy_runner=execute_user_strategy,
            backtest_engine_class=wf_engine,
            n_splits=n_splits,
            train_ratio=train_ratio,
            anchored=anchored,
            inner_optimizer=wf_inner_code,
            inner_n_trials=inner_n_trials,
            inner_objective=wf_metric,
        )

        # 自動判斷交易方向：策略有 short 訊號 → long_short，否則 long
        _r = execute_user_strategy(wf_code, df, wf_fixed)
        if isinstance(_r, tuple) and len(_r) == 7:
            _, _, _, _le, _, _se, _ = _r
            direction_code = "long_short" if (_se is not None and _se.any()) else "long"
        else:
            direction_code = "long"

        with st.spinner(f"Walk-Forward 驗證中（內部優化器: {wf_inner_opt}，可能需要幾分鐘）..."):
            wf_results = validator.run(
                df, wf_code,
                param_space=wf_param_space,
                param_specs=wf_param_specs,
                base_params=wf_fixed,
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
            st.success(f" 完成 {wf_results['n_windows']} 個區段的驗證")

            st.subheader("綜合 OOS 表現")
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

            st.subheader("過擬合風險評估")
            col_od1, col_od2, col_od3 = st.columns(3)
            with col_od1:
                st.metric("平均訓練指標", f"{wf_results['avg_train_metric']:.2f}")
            with col_od2:
                st.metric("平均測試指標", f"{wf_results['avg_test_metric']:.2f}")
            with col_od3:
                deg = wf_results["degradation_pct"]
                st.metric("指標衰退率", f"{deg:+.1f}%", delta="越小越好")

            if deg < 30:
                st.success(" 過擬合風險低：訓練與測試指標接近，泛化能力強")
            elif deg < 60:
                st.warning(" 過擬合風險中等：訓練表現優於測試，建議保守倉位")
            else:
                st.error(" 過擬合風險高：策略可能在真實市場失效")

            st.subheader("參數穩定度分析")
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

            st.subheader("各區段詳細結果")
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
st.caption(" 免責聲明：本工具僅供研究與教育用途。回測結果不代表未來表現。")
