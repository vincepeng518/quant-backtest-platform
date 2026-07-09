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
        "bg": "#020617",            # 深背景
        "bg_subtle": "#0E1223",     # 卡片底色
        "bg_card": "#0F172A",       # slate-900
        "border": "#1E293B",        # slate-800
        "border_strong": "#334155", # slate-700
        "text_primary": "#F8FAFC",  # slate-50
        "text_secondary": "#94A3B8",# slate-400
        "text_muted": "#64748B",    # slate-500
        "primary": "#3B82F6",       # blue-500（亮一點對暗底）
        "primary_hover": "#60A5FA",
        "green": "#22C55E",         # 獲利（亮綠）
        "green_light": "rgba(34, 197, 94, 0.15)",
        "green_text": "#4ADE80",    # green-400
        "red": "#EF4444",
        "red_light": "rgba(239, 68, 68, 0.15)",
        "red_text": "#F87171",      # red-400
        "orange": "#F59E0B",
        "purple": "#A78BFA",
        "yellow": "#FACC15",
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
    padding-top: 2rem;
    max-width: 1280px;
}}

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

/* === 隱藏預設 UI 元素 === */
#MainMenu {{visibility: hidden;}}
footer {{visibility: hidden;}}
[data-testid="stToolbar"] {{visibility: hidden;}}
[data-testid="stDecoration"] {{visibility: hidden;}}
</style>
"""
