"""
主題系統（v7 改進：語意化 CSS Variables + TradingView 配色）

設計原則：
- Light Pro：柔和的淺灰（#F8FAFC），文字 #0F172A
- Dark Trading：深藍灰（#131722，TradingView 真實色），文字 #D1D4DC（避免純白）
- 透過語意化的 CSS 變數（如 --bg-primary, --text-primary）切換
- 切換時只需改變 <html> 或 <body> 的 data-theme 屬性，全站連動
- Plotly 圖表透過 streamlit rerun 自動重新渲染
"""

from typing import Dict


# === 主題配色（語意化）===
# 注意：dark 模式避免使用純黑/純白，參考 TradingView 配色
THEMES: Dict[str, Dict[str, str]] = {
    "light": {
        "name": "Light Pro",
        "id": "light",
        "bg_primary": "#FFFFFF",
        "bg_subtle": "#F9F9F9",
        "bg_card": "#FFFFFF",
        "border": "rgba(0,0,0,0.06)",
        "border_strong": "rgba(0,0,0,0.10)",
        "text_primary": "#1A1A1A",
        "text_secondary": "#6B6B6B",
        "text_muted": "#A0A0A0",
        "primary": "#2563EB",
        "primary_hover": "#1D4ED8",
        "green": "#0D9488",
        "green_light": "rgba(13, 148, 136, 0.08)",
        "green_text": "#0D9488",
        "red": "#EF4444",
        "red_light": "rgba(239, 68, 68, 0.06)",
        "red_text": "#EF4444",
        "orange": "#F97316",
        "purple": "#7C3AED",
        "yellow": "#EAB308",
        "font_family": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang TC', 'Microsoft JhengHei', sans-serif",
        "font_mono": "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace",
        "plotly_template": "plotly_white",
        "plotly_paper": "rgba(0,0,0,0)",
        "plotly_plot": "rgba(0,0,0,0)",
        "plotly_grid": "rgba(0,0,0,0.04)",
        "plotly_axis": "#A0A0A0",
        "plotly_text": "#1A1A1A",
        "radius": "0px",
        "radius_sm": "0px",
        "shadow": "none",
        "shadow_strong": "none",
        "space_xs": "4px",
        "space_sm": "8px",
        "space_md": "12px",
        "space_lg": "16px",
        "space_xl": "24px",
        "space_2xl": "32px",
    },
    "dark": {
        "name": "Dark Trading",
        "id": "dark",
        "bg_primary": "#0D0D0D",
        "bg_subtle": "#161616",
        "bg_card": "#0D0D0D",
        "border": "rgba(255,255,255,0.06)",
        "border_strong": "rgba(255,255,255,0.10)",
        "text_primary": "#E5E5E5",
        "text_secondary": "#8B8B8B",
        "text_muted": "#5C5C5C",
        "primary": "#2962FF",
        "primary_hover": "#1E53E5",
        "green": "#0D9488",
        "green_light": "rgba(13, 148, 136, 0.10)",
        "green_text": "#2DD4BF",
        "red": "#EF5350",
        "red_light": "rgba(239, 83, 80, 0.08)",
        "red_text": "#EF5350",
        "orange": "#FF9800",
        "purple": "#9C27B0",
        "yellow": "#FFEB3B",
        "font_family": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang TC', 'Microsoft JhengHei', sans-serif",
        "font_mono": "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace",
        "plotly_template": "plotly_dark",
        "plotly_paper": "rgba(0,0,0,0)",
        "plotly_plot": "rgba(0,0,0,0)",
        "plotly_grid": "rgba(255,255,255,0.04)",
        "plotly_axis": "#5C5C5C",
        "plotly_text": "#E5E5E5",
        "radius": "0px",
        "radius_sm": "0px",
        "shadow": "none",
        "shadow_strong": "none",
        "space_xs": "4px",
        "space_sm": "8px",
        "space_md": "12px",
        "space_lg": "16px",
        "space_xl": "24px",
        "space_2xl": "32px",
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


# === 向下相容：保留舊的 key 別名 ===
def _migrate_theme(theme: Dict[str, str]) -> Dict[str, str]:
    """向下相容：補上舊的 key 別名，給現有程式碼用。"""
    aliases = {
        "bg": "bg_primary",
        "border_strong": "border_strong",  # 已是新名
    }
    out = dict(theme)
    if "bg" not in out and "bg_primary" in out:
        out["bg"] = out["bg_primary"]
    return out


def css_variables(theme: Dict[str, str]) -> str:
    """產生 CSS variables 區塊，用於 :root 或 [data-theme="..."]。

    用法：
        <html data-theme="light"> ... <style>:root, [data-theme="light"] { --bg-primary: #F8FAFC; ... }</style>
    """
    # 列出所有想暴露為 CSS variables 的 key
    keys = [
        "bg_primary", "bg_subtle", "bg_card",
        "border", "border_strong",
        "text_primary", "text_secondary", "text_muted",
        "primary", "primary_hover",
        "green", "green_light", "green_text",
        "red", "red_light", "red_text",
        "orange", "purple", "yellow",
        "font_family", "font_mono",
        "plotly_paper", "plotly_plot", "plotly_grid", "plotly_axis", "plotly_text",
        "radius", "radius_sm", "shadow", "shadow_strong",
        "space_xs", "space_sm", "space_md", "space_lg", "space_xl", "space_2xl",
    ]
    lines = []
    for k in keys:
        if k in theme:
            val = theme[k]
            # CSS var 名稱轉換：bg_primary → --bg-primary
            css_name = "--" + k.replace("_", "-")
            lines.append(f"  {css_name}: {val};")
    return "\n".join(lines)


def theme_css(theme: Dict[str, str]) -> str:
    """產生主題對應的完整 CSS（v7：CSS Variables + 純 CSS 結構）

    設計重點：
    1. 顏色全部用 var(--xxx) 引用，不寫死 hex
    2. [data-theme="light"] 和 [data-theme="dark"] 切換 variables
    3. Plotly 圖表內部樣式也用 var()，切換主題時即時變色
    4. 所有元素都有 transition，切換時平滑過渡
    """
    # 確保向下相容（如果呼叫方傳舊版 theme dict）
    theme = _migrate_theme(theme)
    theme_id = theme.get("id", "light")

    # 對方/暗色 CSS variables（一次生成兩組，CSS 自動根據 data-theme 切換）
    light_vars = css_variables(THEMES["light"])
    dark_vars = css_variables(THEMES["dark"])

    return f"""
<style>
/* === BORDERLESS MAGAZINE UI === */
:root, [data-theme="light"] {{
{light_vars}
}}
[data-theme="dark"] {{
{dark_vars}
}}

/* === 字體系統：Inter + 寬鬆行距 === */
html, body, [class*="css"] {{
    font-family: var(--font-family), "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif;
    font-size: 14px;
    line-height: 1.6;
    letter-spacing: -0.003em;
}}

/* === 頁面背景：單一純色，無紋理 === */
.stApp {{
    background: var(--bg-primary);
    color: var(--text-primary);
    transition: background-color 150ms ease-out, color 150ms ease-out;
}}

.main .block-container {{
    padding-top: 1rem !important;
    margin-top: 0 !important;
    max-width: 1200px;
}}

/* 隱藏 Streamlit 預設 header / footer / decoration */
header[data-testid="stHeader"],
.stAppHeader, [class*="stAppHeader"],
[data-testid="stAppViewBlockContainer"] > div:first-child,
footer, [data-testid="stDecoration"],
[data-testid="stMainMenuButton"],
[data-testid="stBaseButton-header"],
[data-testid="stBaseButton-headerNoPadding"] {{
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    visibility: hidden !important;
    pointer-events: none !important;
}}
.stApp {{ margin-top: 0 !important; }}
[data-testid="stAppViewBlockContainer"] {{ padding-top: 0 !important; }}

/* Manage app / deploy 按鈕 */
a[href*="streamlit.io/cloud"], [class*="deploy"], [class*="Deploy"],
[data-testid="manage-app-button"], [class*="ManageApp"] {{
    display: none !important;
}}

/* === Sidebar：無邊框，僅用背景色區分 === */
[data-testid="stSidebar"] {{
    background: var(--bg-subtle);
    border-right: none;
    color: var(--text-primary) !important;
    transition: background-color 150ms ease-out;
}}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] .stMarkdown {{
    color: var(--text-primary) !important;
}}
[data-testid="stSidebar"] h2 {{
    font-size: 11px !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
    text-transform: none;
    letter-spacing: 0;
    margin-top: 20px !important;
    margin-bottom: 6px !important;
}}

/* === 標題層級：雜誌風 === */
h1 {{
    font-size: 1.75rem !important;
    font-weight: 700 !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.03em !important;
    line-height: 1.2 !important;
}}
h2 {{
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
    margin-top: 24px !important;
    margin-bottom: 8px !important;
}}
h3 {{
    font-size: 1rem !important;
    font-weight: 600 !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.01em !important;
    margin-top: 20px !important;
    margin-bottom: 8px !important;
}}

/* === Tabs：無邊框底線，僅用文字粗細區分 === */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0;
    border-bottom: none;
    background: transparent;
}}
.stTabs [data-baseweb="tab"] {{
    background: transparent;
    border-radius: 0;
    padding: 8px 16px;
    font-size: 0.8125rem;
    font-weight: 400;
    color: var(--text-muted);
    border-bottom: none;
    transition: color 150ms ease-out, opacity 150ms ease-out;
}}
.stTabs [aria-selected="true"] {{
    color: var(--text-primary) !important;
    font-weight: 600 !important;
    border-bottom: none !important;
    background: transparent !important;
}}
.stTabs [data-baseweb="tab"]:hover {{
    color: var(--text-secondary);
    opacity: 0.8;
}}

/* === 按鈕：細線條 Outline 風格 === */
.stButton button {{
    border-radius: 0;
    font-weight: 500;
    font-size: 0.8125rem;
    border: 1px solid var(--border-strong);
    background: transparent;
    color: var(--text-primary);
    transition: opacity 150ms ease-out, border-color 150ms ease-out;
    padding: 0.45rem 1rem;
    min-height: 36px;
    box-shadow: none;
}}
.stButton button:hover {{
    opacity: 0.7;
    border-color: var(--border-strong);
}}
.stButton button:focus {{
    outline: none;
    opacity: 0.6;
}}
.stButton button:active {{
    opacity: 0.5;
    transform: none;
}}
.stButton button[kind="primary"] {{
    background: var(--primary);
    color: white;
    border: none;
    font-weight: 600;
}}
.stButton button[kind="primary"]:hover {{
    opacity: 0.85;
    background: var(--primary);
}}

/* === 輸入框：無邊框底線風格 === */
.stTextInput input, .stTextArea textarea, .stNumberInput input {{
    border-radius: 0;
    border: none;
    border-bottom: 1px solid var(--border-strong);
    font-size: 0.8125rem;
    background: transparent;
    color: var(--text-primary);
    transition: border-color 150ms ease-out;
    padding: 6px 0;
}}
.stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {{
    border-bottom: 1px solid var(--text-primary);
    box-shadow: none;
}}
.stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div {{
    border-radius: 0;
    border: none;
    border-bottom: 1px solid var(--border-strong);
    font-size: 0.8125rem;
    background: transparent;
    color: var(--text-primary);
    transition: border-color 150ms ease-out;
}}

/* === Metric：純文字排版，無卡片框 === */
[data-testid="stMetric"] {{
    background: transparent;
    padding: 4px 0;
    border-radius: 0;
    border: none;
    box-shadow: none;
}}
[data-testid="stMetricValue"] {{
    font-family: var(--font-mono);
    font-weight: 600;
    font-size: 1.125rem;
    text-align: left;
    color: var(--text-primary);
}}
[data-testid="stMetricDelta"] {{
    font-size: 0.75rem;
}}

/* === Expander：無邊框 === */
[data-testid="stExpander"], .streamlit-expanderHeader {{
    border: none !important;
    border-radius: 0 !important;
    background: transparent !important;
}}
.streamlit-expanderContent {{
    background: transparent;
    border: none;
}}

/* === 表格：無分隔線，極簡 === */
.stDataFrame {{
    border: none;
    border-radius: 0;
    overflow: visible;
}}
.stDataFrame table {{
    border-collapse: collapse;
}}
.stDataFrame table thead tr th {{
    font-weight: 600 !important;
    font-size: 0.6875rem !important;
    color: var(--text-muted) !important;
    background: transparent !important;
    border-bottom: 1px solid var(--border) !important;
    text-transform: none;
    letter-spacing: 0;
    padding: 6px 10px !important;
}}
.stDataFrame table tbody tr {{
    border-bottom: none;
}}
.stDataFrame table tbody tr:nth-child(even) {{
    background: transparent;
}}
.stDataFrame table tbody tr:hover {{
    background: var(--bg-subtle) !important;
}}
.stDataFrame table tbody td {{
    font-family: var(--font-mono) !important;
    text-align: right !important;
    font-size: 0.75rem !important;
    color: var(--text-primary) !important;
    border-bottom: none !important;
    padding: 6px 10px !important;
}}

/* === Divider：極淡 === */
hr {{
    margin: 16px 0 !important;
    border: none !important;
    border-top: 1px solid var(--border) !important;
}}

/* === Caption === */
.stCaption, [data-testid="stCaptionContainer"] {{
    color: var(--text-muted) !important;
    font-size: 0.75rem !important;
}}

/* === Hide streamlit chrome === */
#MainMenu {{ visibility: hidden !important; }}

/* === 手機版 === */
@media (max-width: 768px) {{
    .main .block-container {{
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        padding-top: 0.5rem !important;
    }}
}}

/* === 隱藏 0x0 iframe === */
iframe[height="0"] {{
    display: none !important;
}}

/* === Plotly：完全透明背景 === */
.plotly .modebar, .plotly .modebar-container {{ display: none !important; }}
.plotly .plot-container .svg-plot .xy .bglayer .bg {{ fill: transparent !important; }}
.plotly .main-svg {{ background: transparent !important; }}
.plotly .legend text {{
    fill: var(--plotly-text) !important;
    font-weight: 500 !important;
    font-size: 11px !important;
}}
.plotly .xaxislayer-above text, .plotly .yaxislayer-above text,
.plotly .xtick text, .plotly .ytick text {{
    fill: var(--plotly-axis) !important;
    font-size: 10px !important;
}}
.plotly .xaxis line, .plotly .yaxis line,
.plotly .xaxis path, .plotly .yaxis path {{
    stroke: var(--plotly-grid) !important;
}}
.plotly .gridlines path {{
    stroke: var(--plotly-grid) !important;
}}
.plotly .hoverlayer .hovertext {{
    fill: rgba(28, 31, 42, 0.92) !important;
    stroke: rgba(80, 85, 100, 0.2) !important;
}}
.plotly .hovertext text {{ fill: #FFFFFF !important; font-size: 11px !important; }}
.plotly .spikeline {{ stroke: var(--plotly-axis) !important; }}

/* === 統一過渡 === */
.stApp, .main .block-container, [data-testid="stSidebar"] {{
    transition: background-color 150ms ease-out, color 150ms ease-out;
}}

/* === Empty State === */
.empty-state {{
    text-align: center;
    padding: 48px 16px;
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 0.8125rem;
    font-weight: 400;
}}

/* === Skeleton === */
.skeleton {{
    background: linear-gradient(90deg, var(--bg-subtle) 25%, var(--border) 50%, var(--bg-subtle) 75%);
    background-size: 200% 100%;
    animation: skeleton-loading 1.5s infinite ease-in-out;
    border-radius: 0;
}}
@keyframes skeleton-loading {{
    0% {{ background-position: 200% 0; }}
    100% {{ background-position: -200% 0; }}
}}

/* === Impeccable 風格 === */
[data-testid="stSidebar"] h1 {{
    font-size: 11px !important; font-weight: 600 !important;
    color: var(--text-muted) !important;
    text-transform: none; letter-spacing: 0;
    margin-top: 0 !important; margin-bottom: 6px !important; padding: 0 !important;
}}
[data-testid="stSidebar"] [data-testid="stRadio"] > div {{ gap: 2px !important; }}
[data-testid="stSidebar"] [data-testid="stRadio"] label {{
    padding: 3px 0 !important; font-size: 0.8125rem !important;
}}
[data-testid="stSidebar"] details,
[data-testid="stSidebar"] [data-testid="stExpander"] {{
    border: none !important;
    border-radius: 0 !important;
    background: transparent !important;
    margin-bottom: 4px !important;
}}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
    color: var(--text-muted) !important; font-size: 0.6875rem !important;
}}
[data-testid="stSidebar"] [data-baseweb="select"] {{ font-size: 0.8125rem !important; }}
[data-testid="stSidebar"] .stButton button {{
    min-height: 32px !important; padding: 0.35rem 0.75rem !important; font-size: 0.75rem !important;
}}
[data-testid="stSidebar"] [data-testid="stNumberInput"] input {{
    font-size: 0.8125rem !important; padding: 4px 0 !important;
}}
[data-testid="stSidebar"] [data-testid="stCheckbox"] {{ font-size: 0.8125rem !important; }}

.main h1 {{
    font-size: 1.5rem !important; font-weight: 700 !important;
    letter-spacing: -0.03em !important;
    margin-top: 0.5rem !important; margin-bottom: 0.25rem !important;
}}
.main h2 {{
    font-size: 0.75rem !important; font-weight: 600 !important;
    color: var(--text-muted) !important;
    text-transform: none !important; letter-spacing: 0 !important;
    margin-top: 20px !important; margin-bottom: 8px !important;
}}
.main h3 {{
    font-size: 0.9375rem !important; font-weight: 600 !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.01em !important;
    margin-top: 16px !important; margin-bottom: 6px !important;
}}
.main [data-testid="stCaptionContainer"] {{
    color: var(--text-muted) !important; font-size: 0.75rem !important;
    margin-top: 0 !important; margin-bottom: 8px !important;
}}
.stAlert[data-baseweb="notification"] {{
    border-radius: 0 !important; padding: 6px 0 !important; font-size: 0.8125rem !important;
    border: none !important; background: transparent !important;
}}
[data-testid="stTextArea"] textarea {{
    font-family: var(--font-mono) !important; font-size: 12px !important;
    line-height: 1.6 !important; border-radius: 0 !important;
    background: var(--bg-subtle) !important; border: none !important;
    border-bottom: 1px solid var(--border) !important;
    padding: 10px 12px !important;
}}
[data-testid="stTextArea"] textarea:focus {{
    border-bottom: 1px solid var(--text-primary) !important;
    box-shadow: none !important;
}}
.main [data-testid="stSlider"] {{ padding: 0 !important; }}
.main [data-testid="stDataFrameResizable"] {{
    border: none !important; border-radius: 0 !important;
}}
.main [data-testid="stExpander"] {{
    border: none !important; border-radius: 0 !important;
    background: transparent !important; margin-bottom: 4px !important;
}}
.main [data-testid="stProgress"] > div > div {{ background: var(--primary) !important; }}
.main [data-testid="stSpinner"] > div {{
    padding: 4px 0 !important; font-size: 0.8125rem !important;
}}
.main .stTabs [aria-selected="true"] {{
    color: var(--text-primary) !important; font-weight: 600 !important;
    border-bottom: none !important;
}}
.main .stTabs [data-baseweb="tab"] {{ font-size: 0.8125rem !important; }}
.main-header {{
    font-size: 1.5rem !important; font-weight: 700 !important;
    letter-spacing: -0.03em !important; margin-bottom: 4px !important;
}}
.sub-header {{
    font-size: 0.8125rem !important; color: var(--text-muted) !important;
    margin-bottom: 16px !important;
}}
.impeccable-field-label {{
    font-size: 0.75rem !important; font-weight: 600 !important;
    text-transform: none !important; letter-spacing: 0 !important;
    color: var(--text-muted) !important;
    margin-bottom: 2px !important; display: block;
}}
.impeccable-result-table {{
    width: 100%; border-collapse: collapse;
    font-size: 0.75rem; font-family: var(--font-mono);
}}
.impeccable-result-table th {{
    text-align: left; font-size: 0.6875rem;
    text-transform: none; letter-spacing: 0;
    color: var(--text-muted);
    padding: 6px 8px; border-bottom: 1px solid var(--border); font-weight: 600;
}}
.impeccable-result-table td {{
    padding: 6px 8px; border-bottom: none;
    color: var(--text-primary);
    text-align: right;
}}
.impeccable-num-pill {{
    display: inline-block; padding: 1px 6px; border-radius: 0;
    font-family: var(--font-mono); font-size: 0.6875rem; font-weight: 600;
}}
.impeccable-num-pill.success {{ background: var(--green-light); color: var(--green-text); }}
.impeccable-num-pill.error {{ background: var(--red-light); color: var(--red-text); }}
.impeccable-num-pill.neutral {{ background: var(--bg-subtle); color: var(--text-primary); }}

/* Selectbox dropdowns */
.stSelectbox [data-baseweb="select"] > div {{
    background: transparent !important;
    color: var(--text-primary) !important;
}}
[data-testid="stSelectbox"] .react-aria-ComboBox > div,
[data-testid="stSelectboxVirtual"] .react-aria-ComboBox > div,
[data-testid="stMultiSelect"] .react-aria-ComboBox > div {{
    background: transparent !important;
    color: var(--text-primary) !important;
}}
.stSelectbox [data-baseweb="select"] input {{
    color: var(--text-primary) !important;
    caret-color: var(--text-primary) !important;
}}
[data-baseweb="popover"] [data-baseweb="select-option"] {{
    background: var(--bg-primary) !important; color: var(--text-primary) !important;
}}
[data-baseweb="popover"] [data-baseweb="select-option"]:hover {{
    background: var(--bg-subtle) !important;
}}

.stCodeBlock, code, pre {{
    border-radius: 0 !important; font-size: 0.75rem !important;
    border: none !important; border-bottom: 1px solid var(--border) !important;
}}
</style>

<script>
(function() {{
    function updateSidebarState() {{
        var sidebar = document.querySelector('[data-testid="stSidebar"]');
        if (!sidebar) return;
        var expanded = sidebar.getAttribute('aria-expanded') === 'true';
        if (expanded) document.body.classList.remove('sidebar-collapsed');
        else document.body.classList.add('sidebar-collapsed');
    }}
    var observer = new MutationObserver(updateSidebarState);
    function startObserving() {{
        var sidebar = document.querySelector('[data-testid="stSidebar"]');
        if (sidebar) {{
            observer.observe(sidebar, {{ attributes: true, attributeFilter: ['aria-expanded'] }});
            updateSidebarState();
        }}
    }}
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', startObserving);
    else startObserving();
    setTimeout(startObserving, 500);
    var bodyObserver = new MutationObserver(function() {{
        var sidebar = document.querySelector('[data-testid="stSidebar"]');
        if (sidebar && !sidebar._observed) {{
            sidebar._observed = true;
            observer.observe(sidebar, {{ attributes: true, attributeFilter: ['aria-expanded'] }});
            updateSidebarState();
        }}
    }});
    bodyObserver.observe(document.body, {{ childList: true, subtree: true }});
}})();
</script>
"""
