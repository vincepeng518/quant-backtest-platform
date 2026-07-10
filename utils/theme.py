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
        "green": "#16A34A",         # 獲利（深一點更顯眼）
        "green_light": "#DCFCE7",
        "green_text": "#15803D",    # green-700
        "red": "#DC2626",           # 虧損（深一點更顯眼）
        "red_light": "#FEE2E2",
        "red_text": "#B91C1C",      # red-700
        "orange": "#EA580C",        # Buy & Hold（深一點在淺色也顯眼）
        "purple": "#7C3AED",
        "yellow": "#CA8A04",
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
        "text_primary": "#F8FAFC",  # slate-50（更亮的白）
        "text_secondary": "#CBD5E1",# slate-300
        "text_muted": "#94A3B8",    # slate-400
        "primary": "#60A5FA",       # blue-400（亮一點對暗底）
        "primary_hover": "#93C5FD",
        "green": "#22C55E",         # 獲利（更顯眼）
        "green_light": "rgba(74, 222, 128, 0.15)",
        "green_text": "#4ADE80",    # green-400
        "red": "#EF4444",
        "red_light": "rgba(248, 113, 113, 0.15)",
        "red_text": "#F87171",      # red-400
        "orange": "#FB923C",        # Buy & Hold（亮橙在深色底明顯）
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
    color: {theme['text_primary']} !important;
}}
/* 深色模式：強制覆蓋 streamlit 預設的深色文字 */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] .stMarkdown {{
    color: {theme['text_primary']} !important;
}}
/* 淺色模式：sidebar header (h2) 用 secondary 顏色 */
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

/* === 全域：隱藏 streamlit 內建漢堡按鈕（用我們自製 FAB） === */
/* 因為我們用 #mobile-hamburger-fab 取代它 */
button[data-testid="stBaseButton-headerNoPadding"] {{
    display: none !important;
    visibility: hidden !important;
    pointer-events: none !important;
    width: 0 !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    overflow: hidden !important;
    position: absolute !important;
    top: -9999px !important;
    left: -9999px !important;
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

/* 桌面版：FAB 整合到 sidebar header 右側（取代 streamlit 內建按鈕） */
@media (min-width: 769px) {{
    #mobile-hamburger-fab {{
        display: flex !important;
        /* sidebar header 的最右側（預設值，JS 會動態覆蓋）
         * sidebar 預設寬度 300px，按鈕 44px，右側留 8px
         * → left = 300 - 44 - 8 = 248px */
        top: 4px;
        left: 248px;
    }}
    /* sidebar 收合時 → 移到最左上角（用 !important 蓋過 JS 設定） */
    body.sidebar-collapsed #mobile-hamburger-fab {{
        left: 12px !important;
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

/* === Impeccable 風格增強（第二階段） === */
/* sidebar h1 移除 emoji，section 用 uppercase tracking */
[data-testid="stSidebar"] h1 {{
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    color: {theme['text_secondary']} !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 0 !important;
    margin-bottom: 10px !important;
    padding: 0 !important;
}}

/* sidebar radio button 緊湊 */
[data-testid="stSidebar"] [data-testid="stRadio"] > div {{
    gap: 4px !important;
}}
[data-testid="stSidebar"] [data-testid="stRadio"] label {{
    padding: 4px 0 !important;
    font-size: 0.8125rem !important;
}}

/* sidebar 內 stExpander 視覺化（Impeccable 風格） */
[data-testid="stSidebar"] details,
[data-testid="stSidebar"] [data-testid="stExpander"] {{
    border: 1px solid {theme['border']} !important;
    border-radius: 6px !important;
    background: {theme['bg_card']} !important;
    margin-bottom: 6px !important;
}}

/* sidebar 內 caption 統一 secondary 灰色 */
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
    color: {theme['text_muted']} !important;
    font-size: 0.75rem !important;
}}

/* sidebar 內 selectbox 簡化 */
[data-testid="stSidebar"] [data-baseweb="select"] {{
    font-size: 0.8125rem !important;
}}

/* sidebar 內 button 緊湊 */
[data-testid="stSidebar"] .stButton button {{
    min-height: 34px !important;
    padding: 0.4rem 0.75rem !important;
    font-size: 0.8125rem !important;
}}

/* sidebar 內 number input 緊湊 */
[data-testid="stSidebar"] [data-testid="stNumberInput"] input {{
    font-size: 0.8125rem !important;
    padding: 0.25rem 0.5rem !important;
}}

/* sidebar 內 checkbox 緊湊 */
[data-testid="stSidebar"] [data-testid="stCheckbox"] {{
    font-size: 0.8125rem !important;
}}

/* 主區 h1 統一 Impeccable 風格（不要 emoji 大標）*/
.main h1 {{
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    margin-top: 0.5rem !important;
    margin-bottom: 0.25rem !important;
}}

/* 主區 h2 Impeccable 風格（uppercase tracking） */
.main h2 {{
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    color: {theme['text_secondary']} !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    margin-top: 20px !important;
    margin-bottom: 10px !important;
}}

/* 主區 h3 Impeccable 風格 */
.main h3 {{
    font-size: 0.875rem !important;
    font-weight: 600 !important;
    color: {theme['text_secondary']} !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    margin-top: 16px !important;
    margin-bottom: 8px !important;
}}

/* 主區 caption 統一 */
.main [data-testid="stCaptionContainer"] {{
    color: {theme['text_secondary']} !important;
    font-size: 0.8125rem !important;
    margin-top: 0 !important;
    margin-bottom: 12px !important;
}}

/* 主區空狀態信息條（取代 st.info 大塊藍） */
.stAlert[data-baseweb="notification"] {{
    border-radius: 6px !important;
    padding: 8px 12px !important;
    font-size: 0.8125rem !important;
}}

/* 主區 text_area 程式碼編輯器 Impeccable 風格 */
[data-testid="stTextArea"] textarea {{
    font-family: {theme['font_mono']} !important;
    font-size: 12.5px !important;
    line-height: 1.55 !important;
    border-radius: 6px !important;
    background: {theme['bg_card']} !important;
    border: 1px solid {theme['border']} !important;
    padding: 12px 14px !important;
}}
[data-testid="stTextArea"] textarea:focus {{
    border-color: {theme['primary']} !important;
    box-shadow: 0 0 0 3px {theme['primary']}20 !important;
}}

/* 主區 slider 緊湊 */
.main [data-testid="stSlider"] {{
    padding: 0 !important;
}}

/* 主區 data_editor 表格 Impeccable 風格 */
.main [data-testid="stDataFrameResizable"] {{
    border: 1px solid {theme['border']} !important;
    border-radius: 6px !important;
}}

/* 主區 expander Impeccable 風格 */
.main [data-testid="stExpander"] {{
    border: 1px solid {theme['border']} !important;
    border-radius: 6px !important;
    background: {theme['bg_card']} !important;
    margin-bottom: 8px !important;
}}

/* 主區 progress bar Impeccable 風格 */
.main [data-testid="stProgress"] > div > div {{
    background: {theme['primary']} !important;
}}

/* 主區 spinner 改為更緊湊 */
.main [data-testid="stSpinner"] > div {{
    padding: 4px 0 !important;
    font-size: 0.875rem !important;
}}

/* 主區 tabs 改善（active 顯示更明顯） */
.main .stTabs [aria-selected="true"] {{
    color: {theme['primary']} !important;
    font-weight: 600 !important;
    border-bottom: 2px solid {theme['primary']} !important;
}}
.main .stTabs [data-baseweb="tab"] {{
    font-size: 0.875rem !important;
}}

/* 移除預設 .main-header 樣式衝突（Impeccable 風格） */
.main-header {{
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    margin-bottom: 4px !important;
}}
.sub-header {{
    font-size: 0.875rem !important;
    color: {theme['text_secondary']} !important;
    margin-bottom: 20px !important;
}}

/* Impeccable 副標籤（小 label 在 widget 上方） */
.impeccable-field-label {{
    font-size: 0.6875rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: {theme['text_secondary']} !important;
    margin-bottom: 4px !important;
    display: block;
}}

/* Impeccable 結果表格（替代 st.dataframe 對齊） */
.impeccable-result-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8125rem;
    font-family: {theme['font_mono']};
}}
.impeccable-result-table th {{
    text-align: left;
    font-size: 0.6875rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: {theme['text_secondary']};
    padding: 8px 12px;
    border-bottom: 1px solid {theme['border']};
    font-weight: 600;
}}
.impeccable-result-table td {{
    padding: 8px 12px;
    border-bottom: 1px solid {theme['border']};
    color: {theme['text_primary']};
}}
.impeccable-result-table tr:last-child td {{
    border-bottom: none;
}}

/* Impeccable number-pill（KPI 結果用） */
.impeccable-num-pill {{
    display: inline-block;
    padding: 1px 8px;
    border-radius: 4px;
    font-family: {theme['font_mono']};
    font-size: 0.75rem;
    font-weight: 600;
}}
.impeccable-num-pill.success {{ background: {theme['green_light']}; color: {theme['green_text']}; }}
.impeccable-num-pill.error {{ background: {theme['red_light']}; color: {theme['red_text']}; }}
.impeccable-num-pill.neutral {{ background: {theme['bg_subtle']}; color: {theme['text_primary']}; }}

/* === Streamlit selectbox 容器（深色模式重點修） === */
/* 淺色模式：selectbox 容器白底深字 */
/* 深色模式：selectbox 容器深底淺字（避免黑字在白底） */
.stSelectbox [data-baseweb="select"] > div {{
    background: {theme['bg_card']} !important;
    color: {theme['text_primary']} !important;
    border: 1px solid {theme['border_strong']} !important;
}}
/* 覆蓋 streamlit emotion-cache 內層（這層是純白，bug 源） */
.stSelectbox [data-testid="stSelectbox"] > div:not([class*="react-aria"]) {{
    background: {theme['bg_card']} !important;
}}
/* React Aria combobox 容器：覆蓋白底 */
[data-testid="stSelectbox"] .react-aria-ComboBox > div,
[data-testid="stSelectboxVirtual"] .react-aria-ComboBox > div,
[data-testid="stMultiSelect"] .react-aria-ComboBox > div {{
    background: {theme['bg_card']} !important;
    color: {theme['text_primary']} !important;
    border: 1px solid {theme['border_strong']} !important;
}}
.stSelectbox [data-baseweb="select"] input {{
    color: {theme['text_primary']} !important;
    caret-color: {theme['text_primary']} !important;
}}
.stSelectbox [data-baseweb="select"] > div > div {{
    color: {theme['text_primary']} !important;
}}
/* 修正 selectbox 內 svg（箭頭）顏色 */
.stSelectbox [data-baseweb="select"] svg,
.stSelectbox button svg {{
    fill: {theme['text_secondary']} !important;
    color: {theme['text_secondary']} !important;
}}

/* selectbox dropdown 開啟時的 listbox（portal 渲染） */
[data-baseweb="popover"] [data-baseweb="select-option"] {{
    background: {theme['bg_card']} !important;
    color: {theme['text_primary']} !important;
}}
[data-baseweb="popover"] [data-baseweb="select-option"]:hover {{
    background: {theme['bg_subtle']} !important;
}}
[data-baseweb="popover"] [data-baseweb="select-option"][aria-selected="true"] {{
    background: {theme['primary']} !important;
    color: white !important;
}}

/* multiselect 同 selectbox */
.stMultiSelect [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div > div {{
    background: {theme['bg_card']} !important;
    color: {theme['text_primary']} !important;
}}
.stMultiSelect [data-baseweb="select"] svg {{
    fill: {theme['text_secondary']} !important;
    color: {theme['text_secondary']} !important;
}}

/* st.info / st.success / st.warning / st.error Impeccable 化（緊湊） */
.stAlert {{
    border-radius: 6px !important;
    padding: 8px 14px !important;
    font-size: 0.8125rem !important;
}}

/* st.code 區塊（蒙地卡羅結果等） */
.stCodeBlock, code, pre {{
    border-radius: 6px !important;
    font-size: 0.8125rem !important;
    border: 1px solid {theme['border']} !important;
}}

/* === v4 改進：Top Bar 主題切換 + 動畫 === */
/* 主題切換平滑過渡（所有 element） */
.stApp, .main .block-container, [data-testid="stSidebar"],
.stButton button, .stTextInput input, .stTextArea textarea,
.stSelectbox [data-baseweb="select"], [data-testid="stMetric"] {{
    transition: background-color 200ms ease, color 200ms ease,
                border-color 200ms ease, box-shadow 200ms ease !important;
}}

/* Plotly 圖表層次加強（深色模式圖例更顯眼） */
.plotly .legend text {{
    fill: {theme['text_primary']} !important;
    font-weight: 500 !important;
}}
.plotly .modebar-btn path {{
    fill: {theme['text_secondary']} !important;
}}
.plotly .modebar-btn:hover path {{
    fill: {theme['primary']} !important;
}}

/* Plotly 坐標軸文字（深色模式更亮） */
.plotly .xaxislayer-above text, .plotly .yaxislayer-above text,
.plotly .xtick text, .plotly .ytick text {{
    fill: {theme['text_secondary']} !important;
}}

/* Plotly hover 標籤（深色模式更亮） */
.plotly .hovertext text {{
    fill: {theme['text_primary']} !important;
}}
.plotly .spikeline {{
    stroke: {theme['text_secondary']} !important;
}}

/* === v4 改進：Top Bar 切換按鈕（右上角浮動） === */
#theme-toggle-fab {{
    position: fixed;
    top: 12px;
    right: 12px;
    z-index: 999998;
    width: 44px;
    height: 44px;
    min-width: 44px;
    min-height: 44px;
    border-radius: 50%;
    background: {theme['bg_card']};
    color: {theme['text_primary']};
    border: 1.5px solid {theme['border_strong']};
    box-shadow: 0 4px 16px rgba(0,0,0,{0.15 if theme['bg'] != '#0F172A' else 0.4});
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    padding: 0;
    margin: 0;
    font-size: 0;
    line-height: 1;
    -webkit-tap-highlight-color: transparent;
    transition: transform 200ms ease, background 200ms ease, border-color 200ms ease, color 200ms ease;
    outline: none !important;
    -webkit-appearance: none !important;
    appearance: none !important;
}}
#theme-toggle-fab:hover {{
    transform: scale(1.08);
    border-color: {theme['primary']};
    background: {theme['primary']};
    color: white;
}}
#theme-toggle-fab:focus,
#theme-toggle-fab:focus-visible,
#theme-toggle-fab:focus-within {{
    outline: none !important;
    box-shadow: 0 0 0 3px {theme['primary']}40, 0 4px 16px rgba(0,0,0,{0.15 if theme['bg'] != '#0F172A' else 0.4}) !important;
}}
#theme-toggle-fab:active {{
    transform: scale(0.95);
}}
#theme-toggle-fab svg {{
    width: 22px;
    height: 22px;
    fill: currentColor;
    pointer-events: none;
}}

/* Top Bar 隱藏內建 streamlit header（避免 FAB 衝突） */
[data-testid="stHeader"] {{
    z-index: 999997;
}}

/* FAB 圖示旋轉動畫（切換時） */
#theme-toggle-fab.switching svg {{
    animation: rotateTheme 400ms cubic-bezier(0.4, 0, 0.2, 1);
}}
@keyframes rotateTheme {{
    from {{ transform: rotate(0deg); }}
    to {{ transform: rotate(360deg); }}
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
