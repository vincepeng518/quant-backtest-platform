"""
主題系統（基於 ui-ux-pro-max 設計規則）
- Light Pro：#28 Data-Dense Dashboard（亮色金融儀表板）
- Dark Trading：#6 Financial Dashboard（暗色 TradingView 風格）
- 透過 st.session_state["theme"] 切換
"""

from typing import Dict


# === 主題配色 ===
THEMES: Dict[str, Dict[str, str]] = {
    # Data-Dense Dashboard 亮色（金融工具首選）
    "light": {
        "name": "🌞 Light Pro",
        "id": "light",
        "bg": "#F8FAFC",            # slate-50 頁面背景
        "bg_subtle": "#F1F5F9",     # slate-100 區塊背景
        "bg_card": "#FFFFFF",       # 卡片白
        "border": "#E2E8F0",        # slate-200 細邊框
        "border_strong": "#CBD5E1", # slate-300
        "text_primary": "#0F172A",  # slate-900
        "text_secondary": "#475569",# slate-600
        "text_muted": "#94A3B8",    # slate-400
        "primary": "#2563EB",       # blue-600 主色
        "primary_hover": "#1D4ED8", # blue-700
        "green": "#22C55E",         # 獲利
        "green_light": "#DCFCE7",
        "green_text": "#15803D",    # green-700
        "red": "#EF4444",           # 虧損
        "red_light": "#FEE2E2",
        "red_text": "#B91C1C",      # red-700
        "orange": "#F59E0B",        # 警告
        "purple": "#8B5CF6",
        "yellow": "#EAB308",
        "font_family": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang TC', 'Microsoft JhengHei', sans-serif",
        "font_mono": "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace",
        "plotly_template": "plotly_white",
        "radius": "8px",
        "shadow": "0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.06)",
    },
    # Financial Dashboard 暗色（TradingView 風格）
    "dark": {
        "name": "🌙 Dark Trading",
        "id": "dark",
        "bg": "#0F172A",            # slate-900（深藍灰，不要全黑）
        "bg_subtle": "#1E293B",     # slate-800 區塊背景
        "bg_card": "#1E293B",       # slate-800 卡片底
        "border": "#334155",        # slate-700
        "border_strong": "#475569", # slate-600
        "text_primary": "#F1F5F9",  # slate-100（不要太刺眼的白）
        "text_secondary": "#CBD5E1",# slate-300
        "text_muted": "#94A3B8",    # slate-400
        "primary": "#60A5FA",       # blue-400（亮一點對暗底）
        "primary_hover": "#93C5FD",
        "green": "#4ADE80",         # 獲利（亮綠）
        "green_light": "rgba(74, 222, 128, 0.15)",
        "green_text": "#86EFAC",    # green-300
        "red": "#F87171",
        "red_light": "rgba(248, 113, 113, 0.15)",
        "red_text": "#FCA5A5",      # red-300
        "orange": "#FBBF24",
        "purple": "#C4B5FD",
        "yellow": "#FDE047",
        "font_family": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang TC', 'Microsoft JhengHei', sans-serif",
        "font_mono": "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace",
        "plotly_template": "plotly_dark",
        "radius": "6px",
        "shadow": "0 1px 2px rgba(0, 0, 0, 0.4), 0 4px 12px rgba(0, 0, 0, 0.3)",
    },
}


def get_theme(theme_id: str = None) -> Dict[str, str]:
    """取得當前主題配色；若 theme_id 為 None 則用預設 light"""
    if theme_id is None:
        theme_id = "light"
    return THEMES.get(theme_id, THEMES["light"])


def get_current_theme() -> Dict[str, str]:
    """從 Streamlit session_state 取得當前主題"""
    try:
        import streamlit as st
        theme_id = st.session_state.get("theme", "light")
    except Exception:
        theme_id = "light"
    return get_theme(theme_id)


def list_themes() -> Dict[str, str]:
    """回傳 {id: name} 供 selectbox 使用"""
    return {tid: t["name"] for tid, t in THEMES.items()}


def theme_css(theme: Dict[str, str]) -> str:
    """
    產生主題對應的完整 CSS（用於 st.markdown 注入）
    設計規則來源：ui-ux-pro-max-skill
    """
    return f"""
<style>
/* === 字體系統（ux-guidelines: base 16px, line-height 1.5） === */
html, body, [class*="css"] {{
    font-family: {theme['font_family']}, "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", "Twemoji Mozilla", "EmojiOne Color", "Android Emoji", sans-serif;
    font-size: 14px;
    line-height: 1.5;
}}

/* === 頁面背景 === */
.stApp {{
    background: {theme['bg']};
    color: {theme['text_primary']};
}}

.main .block-container {{
    padding-top: 0 !important;
    margin-top: 0 !important;
    max-width: 1280px;
}}

/* 隱藏 Streamlit 預設的頂部空白區（手機上看起來很醜） */
header[data-testid="stHeader"] {{
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}}
.stAppHeader,
[class*="stAppHeader"] {{
    display: none !important;
    height: 0 !important;
}}
[data-testid="stAppViewBlockContainer"] {{
    padding-top: 0 !important;
    margin-top: 0 !important;
}}
.stApp {{
    margin-top: 0 !important;
}}

/* 隱藏 Streamlit Cloud 的「Manage app」按鈕（手機上擋住內容） */
[data-testid="manage-app-button"],
[class*="ManageApp"],
[class*="manage-app"],
a[href*="streamlit.io/cloud"],
div[id*="manage"] {{
    display: none !important;
    visibility: hidden !important;
    pointer-events: none !important;
}}
/* 隱藏 footer（雲端版的 "Hosted with Streamlit"） */
footer {{ display: none !important; }}
/* 隱藏任何「Hosted with」字樣 */
*:not(body):not(html):not(div) {{ /* placeholder */ }}

/* === 標題層級（heading-hierarchy） === */
.main-header {{
    font-size: 1.875rem;
    font-weight: 700;
    color: {theme['text_primary']};
    margin-bottom: 4px;
    letter-spacing: -0.02em;
}}
.sub-header {{
    color: {theme['text_secondary']};
    font-size: 0.875rem;
    margin-top: 0;
    margin-bottom: 28px;
    font-weight: 400;
}}
h1, h2, h3, h4 {{
    color: {theme['text_primary']} !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em;
}}
h3 {{
    font-size: 1.125rem !important;
    margin-top: 24px !important;
    margin-bottom: 12px !important;
}}

/* === Sidebar === */
[data-testid="stSidebar"] {{
    background: {theme['bg_subtle']};
    border-right: 1px solid {theme['border']};
}}
[data-testid="stSidebar"] h2 {{
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    color: {theme['text_secondary']} !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 16px !important;
    margin-bottom: 8px !important;
}}

/* === Tabs（清晰可見的 active state） === */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0;
    border-bottom: 1px solid {theme['border']};
    background: transparent;
}}
.stTabs [data-baseweb="tab"] {{
    background: transparent;
    border-radius: 0;
    padding: 10px 18px;
    font-size: 0.875rem;
    font-weight: 500;
    color: {theme['text_secondary']};
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    transition: color 150ms ease;
}}
.stTabs [aria-selected="true"] {{
    color: {theme['primary']} !important;
    border-bottom: 2px solid {theme['primary']} !important;
    background: transparent !important;
}}
.stTabs [data-baseweb="tab"]:hover {{
    color: {theme['text_primary']};
}}

/* === 按鈕（touch-target 44px min, focus rings） === */
.stButton button {{
    border-radius: {theme['radius']};
    font-weight: 500;
    font-size: 0.875rem;
    border: 1px solid {theme['border_strong']};
    background: {theme['bg_card']};
    color: {theme['text_primary']};
    transition: all 150ms ease;
    padding: 0.5rem 1rem;
    min-height: 38px;
    box-shadow: none;
}}
.stButton button:hover {{
    background: {theme['bg_subtle']};
    border-color: {theme['primary']};
    color: {theme['text_primary']};
}}
.stButton button:focus {{
    outline: 2px solid {theme['primary']};
    outline-offset: 2px;
}}
.stButton button:active {{
    transform: scale(0.98);
}}
.stButton button[kind="primary"] {{
    background: {theme['primary']};
    color: white;
    border: 1px solid {theme['primary']};
    font-weight: 600;
}}
.stButton button[kind="primary"]:hover {{
    background: {theme['primary_hover']};
    border-color: {theme['primary_hover']};
    color: white;
}}

/* === 輸入框（focus 狀態清晰） === */
.stTextInput input, .stTextArea textarea, .stNumberInput input,
.stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div {{
    border-radius: 6px;
    border: 1px solid {theme['border_strong']};
    font-size: 0.875rem;
    background: {theme['bg_card']};
    color: {theme['text_primary']};
    transition: border-color 150ms ease, box-shadow 150ms ease;
}}
.stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {{
    border-color: {theme['primary']};
    box-shadow: 0 0 0 3px {theme['primary']}20;
}}

/* === Metric 卡片（KPI 風格） === */
[data-testid="stMetric"] {{
    background: {theme['bg_card']};
    padding: 12px 16px;
    border-radius: {theme['radius']};
    border: 1px solid {theme['border']};
    box-shadow: {theme['shadow']};
}}
[data-testid="stMetricValue"] {{
    font-family: {theme['font_mono']};
    font-weight: 600;
}}

/* === 展開區塊 === */
.streamlit-expanderHeader {{
    background: {theme['bg_subtle']} !important;
    border-radius: {theme['radius']} !important;
    border: 1px solid {theme['border']} !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    color: {theme['text_primary']} !important;
}}
.streamlit-expanderContent {{
    background: {theme['bg_card']};
    border: 1px solid {theme['border']};
    border-top: none;
    border-radius: 0 0 {theme['radius']} {theme['radius']};
}}

/* === 表格 === */
.stDataFrame {{
    border: 1px solid {theme['border']};
    border-radius: {theme['radius']};
    overflow: hidden;
}}

/* === Divider === */
hr {{
    margin: 20px 0 !important;
    border-color: {theme['border']} !important;
}}

/* === Caption / 註解 === */
.stCaption, [data-testid="stCaptionContainer"] {{
    color: {theme['text_secondary']} !important;
    font-size: 0.8125rem !important;
}}

/* === 隱藏預設 UI 元素（但保留 sidebar 展開按鈕） === */
#MainMenu {{visibility: hidden !important;}}
footer {{visibility: hidden !important;}}
/* 隱藏右上角裝飾 */
[data-testid="stDecoration"] {{visibility: hidden !important;}}
/* 隱藏 toolbar 內的特定按鈕（MainMenu、Deploy 等） */
[data-testid="stMainMenuButton"] {{visibility: hidden !important;}}
[data-testid="stBaseButton-header"] {{visibility: hidden !important;}}
[data-testid="stBaseButton-headerNoPadding"] {{
    color: {theme['primary']} !important;
}}

/* 隱藏 Streamlit Cloud 的 Manage app 元素（任何含 'Manage app' 文字的浮動元素） */
a:has-text("Manage app"),
div:has-text("Manage app"),
.stAppDeployButton {{
    display: none !important;
    visibility: hidden !important;
    pointer-events: none !important;
}}
/* 用 JS 注入隱藏任何底部 Deploy 按鈕 */
[class*="deploy"],
[class*="Deploy"],
a[href*="streamlit.io/cloud"] {{
    display: none !important;
}}

/* === 手機版：明顯的 sidebar 展開按鈕 === */
@media (max-width: 768px) {{
    /* 主內容區加大左 padding 避免被浮動按鈕擋住 */
    .main .block-container {{
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        padding-top: 0.5rem !important;
    }}

    /* === 手機版：隱藏 streamlit 內建的 sidebar 切換按鈕 === */
    /* 用戶只需要看我們的浮動 FAB，避免兩個按鈕混淆 */
    [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] {{
        display: none !important;
        visibility: hidden !important;
    }}

    /* 當 sidebar 收合時，Streamlit 的展開按鈕 — 顯示在左上角 */
    [data-testid="stExpandSidebarButton"] {{
        visibility: visible !important;
        display: flex !important;
        position: fixed !important;
        top: 12px !important;
        left: 12px !important;
        right: auto !important;
        bottom: auto !important;
        z-index: 999998 !important;
        background: {theme['primary']} !important;
        color: white !important;
        border-radius: 50% !important;
        width: 48px !important;
        height: 48px !important;
        min-width: 48px !important;
        min-height: 48px !important;
        max-width: 48px !important;
        max-height: 48px !important;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25) !important;
        border: 2px solid white !important;
        align-items: center !important;
        justify-content: center !important;
        opacity: 1 !important;
        transform: none !important;
        margin: 0 !important;
        padding: 0 !important;
    }}
    /* 強制按鈕內所有元素有大小 */
    [data-testid="stExpandSidebarButton"] * {{
        width: 48px !important;
        height: 48px !important;
        min-width: 48px !important;
        min-height: 48px !important;
    }}
    [data-testid="stExpandSidebarButton"] svg {{
        color: white !important;
        fill: white !important;
        width: 24px !important;
        height: 24px !important;
        margin: auto !important;
    }}
    [data-testid="stExpandSidebarButton"]:hover {{
        background: {theme['primary_hover']} !important;
        transform: scale(1.05) !important;
    }}

    /* 主內容區頂部 padding 縮減 */
    [data-testid="stAppViewBlockContainer"] {{
        padding-top: 0.5rem !important;
    }}
    .main .block-container {{
        padding-top: 0.5rem !important;
    }}

    /* 手機版：sidebar 響應 aria-expanded 切換 */
    [data-testid="stSidebar"][aria-expanded="false"] {{
        transform: translateX(-100%) !important;
        margin-left: -21rem !important;
    }}
    [data-testid="stSidebar"] {{
        transition: transform 200ms ease, margin-left 200ms ease !important;
    }}
    /* 收合時 main 區填滿 */
    .main {{
        margin-left: 0 !important;
        transition: margin-left 200ms ease !important;
    }}
}}

/* === 全域：漢堡按鈕（用 streamlit 預設的 sidebar 切換按鈕） === */
/* streamlit 的 [data-testid="stBaseButton-headerNoPadding"] 就是 sidebar 切換按鈕 */
/* 把它重新樣式為圓形漢堡按鈕（在 sidebar 內或外部顯示） */
button[data-testid="stBaseButton-headerNoPadding"] {{
    background: {theme['primary']} !important;
    color: white !important;
    border-radius: 50% !important;
    width: 44px !important;
    height: 44px !important;
    min-width: 44px !important;
    min-height: 44px !important;
    box-shadow: 0 4px 16px rgba(0,0,0,0.25) !important;
    border: 2px solid white !important;
    z-index: 999999 !important;
}}
button[data-testid="stBaseButton-headerNoPadding"] svg {{
    color: white !important;
    fill: white !important;
}}

/* === 浮動漢堡按鈕（永遠顯示，sidebar 開啟時變成 X 表示關閉） === */
#mobile-hamburger-fab {{
    position: fixed;
    top: 12px;
    left: 12px;
    z-index: 999999;
    width: 44px;
    height: 44px;
    min-width: 44px;
    min-height: 44px;
    border-radius: 50%;
    background: {theme['primary']};
    color: white;
    border: 2px solid white;
    box-shadow: 0 4px 16px rgba(0,0,0,0.25);
    display: flex;          /* 永遠顯示 */
    align-items: center;
    justify-content: center;
    cursor: pointer;
    padding: 0;
    margin: 0;
    font-size: 0;
    line-height: 1;
    -webkit-tap-highlight-color: transparent;
    transition: transform 120ms ease, background 120ms ease;
}}
#mobile-hamburger-fab:hover {{
    background: {theme['primary_hover']};
    transform: scale(1.05);
}}
#mobile-hamburger-fab:active {{
    transform: scale(0.95);
}}
#mobile-hamburger-fab svg {{
    width: 22px;
    height: 22px;
    fill: white;
    color: white;
}}

/* 桌面版：FAB 整合到 sidebar 內（取代 streamlit 內建按鈕） */
@media (min-width: 769px) {{
    #mobile-hamburger-fab {{
        display: flex !important;
        /* sidebar 內的右上角（取代 streamlit 預設按鈕） */
        top: 4px;
        left: 236px;
    }}
    /* sidebar 收合時 → 移到最左上角 */
    body.sidebar-collapsed #mobile-hamburger-fab {{
        left: 12px;
    }}
    /* === 桌面版：隱藏 streamlit 內建 sidebar 切換按鈕 === */
    /* 因為 FAB 在同位置，避免兩個按鈕重疊 */
    [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] {{
        display: none !important;
        visibility: hidden !important;
    }}
}}

/* === 桌面版：隱藏 toolbar 內的展開按鈕（用 sidebar 內的「<」就好） === */
@media (min-width: 769px) {{
    [data-testid="stExpandSidebarButton"] {{display: none;}}
    [data-testid="stToolbar"] {{visibility: hidden;}}
}}

/* === 隱藏 components.html 注入的 0x0 iframe（浮動漢堡按鈕用） === */
iframe[height="0"] {{
    display: none !important;
    height: 0 !important;
    width: 0 !important;
    border: none !important;
    position: absolute !important;
    visibility: hidden !important;
}}
</style>

<script>
(function() {{
    // 監聽 sidebar 收合狀態，自動切換 body class（控制浮動漢堡按鈕顯示/隱藏）
    function updateSidebarState() {{
        var sidebar = document.querySelector('[data-testid="stSidebar"]');
        if (!sidebar) return;
        var expanded = sidebar.getAttribute('aria-expanded') === 'true';
        if (expanded) {{
            document.body.classList.remove('sidebar-collapsed');
        }} else {{
            document.body.classList.add('sidebar-collapsed');
        }}
    }}
    // 用 MutationObserver 監聽 aria-expanded 變化
    var observer = new MutationObserver(updateSidebarState);
    function startObserving() {{
        var sidebar = document.querySelector('[data-testid="stSidebar"]');
        if (sidebar) {{
            observer.observe(sidebar, {{ attributes: true, attributeFilter: ['aria-expanded'] }});
            updateSidebarState();
        }}
    }}
    // 初次啟動 + DOM 變化時重試（streamlit SPA 會換內容）
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', startObserving);
    }} else {{
        startObserving();
    }}
    setTimeout(startObserving, 500);
    setTimeout(startObserving, 2000);
    // 監聽整個 DOM 變化以處理 streamlit 重新渲染
    var bodyObserver = new MutationObserver(function() {{
        var sidebar = document.querySelector('[data-testid="stSidebar"]');
        if (sidebar && !sidebar._observed) {{
            sidebar._observed = true;
            observer.observe(sidebar, {{ attributes: true, attributeFilter: ['aria-expanded'] }});
            updateSidebarState();
        }}
    }});
    bodyObserver.observe(document.body, {{ childList: true, subtree: true }});
    // 每 1 秒檢查一次（保險）
    setInterval(updateSidebarState, 1000);
}})();
</script>
"""
