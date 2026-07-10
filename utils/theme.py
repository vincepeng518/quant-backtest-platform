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
        # === 語意化色彩變數 ===
        # 背景層級
        "bg_primary": "#F8FAFC",       # 頁面主背景（slate-50，柔和淺灰）
        "bg_subtle": "#F1F5F9",        # 區塊背景（slate-100）
        "bg_card": "#FFFFFF",          # 卡片白
        # 邊框
        "border": "#E2E8F0",           # 細邊框（slate-200）
        "border_strong": "#CBD5E1",    # 強調邊框（slate-300）
        # 文字
        "text_primary": "#0F172A",     # 主要文字（slate-900）
        "text_secondary": "#475569",   # 次要文字（slate-600）
        "text_muted": "#94A3B8",       # 弱化文字（slate-400）
        # 主色
        "primary": "#2563EB",          # blue-600
        "primary_hover": "#1D4ED8",    # blue-700
        # 語意色
        "green": "#16A34A",
        "green_light": "#DCFCE7",
        "green_text": "#15803D",
        "red": "#DC2626",
        "red_light": "#FEE2E2",
        "red_text": "#B91C1C",
        "orange": "#EA580C",
        "purple": "#7C3AED",
        "yellow": "#CA8A04",
        # 字體
        "font_family": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang TC', 'Microsoft JhengHei', sans-serif",
        "font_mono": "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace",
        # 圖表
        "plotly_template": "plotly_white",
        "plotly_paper": "#F8FAFC",
        "plotly_plot": "#F8FAFC",
        "plotly_grid": "#E2E8F0",
        "plotly_axis": "#475569",
        "plotly_text": "#0F172A",
        # 形狀
        "radius": "8px",
        "shadow": "0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.06)",
        "shadow_strong": "0 4px 12px rgba(15, 23, 42, 0.08)",
    },
    "dark": {
        "name": "Dark Trading",
        "id": "dark",
        # === 語意化色彩變數（TradingView 暗色配色：#131722 背景，#D1D4DC 文字）===
        "bg_primary": "#131722",       # 頁面主背景（TradingView 真實色，避免純黑）
        "bg_subtle": "#1A1E2A",        # 區塊背景（略淺一點）
        "bg_card": "#1A1E2A",          # 卡片底
        "border": "#2A2E39",           # 細邊框（TV border）
        "border_strong": "#363A45",    # 強調邊框
        "text_primary": "#D1D4DC",     # 主要文字（TV text，避免純白刺眼）
        "text_secondary": "#787B86",   # 次要文字（TV text muted）
        "text_muted": "#5D606B",       # 弱化文字
        "primary": "#2962FF",          # TV blue（用真實的 TV 主色）
        "primary_hover": "#1E53E5",
        "green": "#26A69A",            # TV 上漲綠
        "green_light": "rgba(38, 166, 154, 0.15)",
        "green_text": "#26A69A",
        "red": "#EF5350",              # TV 下跌紅
        "red_light": "rgba(239, 83, 80, 0.15)",
        "red_text": "#EF5350",
        "orange": "#FF9800",           # TV 橘
        "purple": "#9C27B0",
        "yellow": "#FFEB3B",
        "font_family": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang TC', 'Microsoft JhengHei', sans-serif",
        "font_mono": "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace",
        "plotly_template": "plotly_dark",
        "plotly_paper": "#131722",
        "plotly_plot": "#131722",
        "plotly_grid": "#2A2E39",
        "plotly_axis": "#787B86",
        "plotly_text": "#D1D4DC",
        "radius": "6px",
        "shadow": "0 1px 2px rgba(0, 0, 0, 0.3), 0 4px 12px rgba(0, 0, 0, 0.2)",
        "shadow_strong": "0 4px 16px rgba(0, 0, 0, 0.5)",
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
        "radius", "shadow", "shadow_strong",
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
/* === v7 改進：語意化 CSS Variables + TradingView 配色 === */
/* 淺色模式變數（預設） */
:root, [data-theme="light"] {{
{light_vars}
}}

/* 深色模式變數（覆蓋淺色） */
[data-theme="dark"] {{
{dark_vars}
}}

/* === 字體系統 === */
html, body, [class*="css"] {{
    font-family: var(--font-family), "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif;
    font-size: 14px;
    line-height: 1.5;
}}

/* === 頁面背景 === */
.stApp {{
    background: var(--bg-primary);
    color: var(--text-primary);
    /* 全站過渡：切換主題時平滑變色 */
    transition: background-color 250ms ease, color 250ms ease;
}}

.main .block-container {{
    padding-top: 0 !important;
    margin-top: 0 !important;
    max-width: 1280px;
}}

/* 隱藏 Streamlit 預設的頂部空白區 */
header[data-testid="stHeader"] {{
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}}
.stAppHeader, [class*="stAppHeader"] {{
    display: none !important;
    height: 0 !important;
}}
[data-testid="stAppViewBlockContainer"] {{
    padding-top: 0 !important;
    margin-top: 0 !important;
}}
.stApp {{ margin-top: 0 !important; }}

/* 隱藏 Streamlit Cloud 的「Manage app」按鈕 */
[data-testid="manage-app-button"],
[class*="ManageApp"], [class*="manage-app"],
a[href*="streamlit.io/cloud"], div[id*="manage"] {{
    display: none !important; visibility: hidden !important; pointer-events: none !important;
}}
footer {{ display: none !important; }}

/* === 標題層級 === */
.main-header {{
    font-size: 1.875rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 4px;
    letter-spacing: -0.02em;
}}
.sub-header {{
    color: var(--text-secondary);
    font-size: 0.875rem;
    margin-top: 0;
    margin-bottom: 28px;
    font-weight: 400;
}}
h1, h2, h3, h4 {{
    color: var(--text-primary) !important;
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
    background: var(--bg-subtle);
    border-right: 1px solid var(--border);
    color: var(--text-primary) !important;
    transition: background-color 250ms ease, border-color 250ms ease;
}}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] .stMarkdown {{
    color: var(--text-primary) !important;
}}
[data-testid="stSidebar"] h2 {{
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    color: var(--text-secondary) !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 16px !important;
    margin-bottom: 8px !important;
}}

/* === Tabs === */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0;
    border-bottom: 1px solid var(--border);
    background: transparent;
}}
.stTabs [data-baseweb="tab"] {{
    background: transparent;
    border-radius: 0;
    padding: 10px 18px;
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--text-secondary);
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    transition: color 150ms ease, border-color 150ms ease;
}}
.stTabs [aria-selected="true"] {{
    color: var(--primary) !important;
    border-bottom: 2px solid var(--primary) !important;
    background: transparent !important;
}}
.stTabs [data-baseweb="tab"]:hover {{ color: var(--text-primary); }}

/* === 按鈕 === */
.stButton button {{
    border-radius: var(--radius);
    font-weight: 500;
    font-size: 0.875rem;
    border: 1px solid var(--border-strong);
    background: var(--bg-card);
    color: var(--text-primary);
    transition: all 150ms ease;
    padding: 0.5rem 1rem;
    min-height: 38px;
    box-shadow: none;
}}
.stButton button:hover {{
    background: var(--bg-subtle);
    border-color: var(--primary);
    color: var(--text-primary);
}}
.stButton button:focus {{
    outline: 2px solid var(--primary);
    outline-offset: 2px;
}}
.stButton button:active {{ transform: scale(0.98); }}
.stButton button[kind="primary"] {{
    background: var(--primary);
    color: white;
    border: 1px solid var(--primary);
    font-weight: 600;
}}
.stButton button[kind="primary"]:hover {{
    background: var(--primary-hover);
    border-color: var(--primary-hover);
    color: white;
}}

/* === 輸入框 === */
.stTextInput input, .stTextArea textarea, .stNumberInput input,
.stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div {{
    border-radius: 6px;
    border: 1px solid var(--border-strong);
    font-size: 0.875rem;
    background: var(--bg-card);
    color: var(--text-primary);
    transition: border-color 150ms ease, box-shadow 150ms ease, background-color 250ms ease, color 250ms ease;
}}
.stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {{
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.2);
}}

/* === Metric 卡片 === */
[data-testid="stMetric"] {{
    background: var(--bg-card);
    padding: 12px 16px;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    box-shadow: var(--shadow);
    transition: background-color 250ms ease, border-color 250ms ease;
}}
[data-testid="stMetricValue"] {{
    font-family: var(--font-mono);
    font-weight: 600;
}}

/* === 展開區塊 === */
.streamlit-expanderHeader {{
    background: var(--bg-subtle) !important;
    border-radius: var(--radius) !important;
    border: 1px solid var(--border) !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    color: var(--text-primary) !important;
}}
.streamlit-expanderContent {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-top: none;
    border-radius: 0 0 var(--radius) var(--radius);
}}

/* === 表格 === */
.stDataFrame {{
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
}}

/* === Divider === */
hr {{
    margin: 20px 0 !important;
    border-color: var(--border) !important;
}}

/* === Caption === */
.stCaption, [data-testid="stCaptionContainer"] {{
    color: var(--text-secondary) !important;
    font-size: 0.8125rem !important;
}}

/* === 隱藏預設 UI 元素 === */
#MainMenu {{visibility: hidden !important;}}
footer {{visibility: hidden !important;}}
[data-testid="stDecoration"] {{visibility: hidden !important;}}
[data-testid="stMainMenuButton"] {{visibility: hidden !important;}}
[data-testid="stBaseButton-header"] {{visibility: hidden !important;}}
[data-testid="stBaseButton-headerNoPadding"] {{
    color: var(--primary) !important;
}}

a:has-text("Manage app"), div:has-text("Manage app"), .stAppDeployButton {{
    display: none !important; visibility: hidden !important; pointer-events: none !important;
}}
[class*="deploy"], [class*="Deploy"], a[href*="streamlit.io/cloud"] {{
    display: none !important;
}}

/* === 手機版：sidebar 切換按鈕 === */
@media (max-width: 768px) {{
    .main .block-container {{
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        padding-top: 0.5rem !important;
    }}
    [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] {{
        display: none !important; visibility: hidden !important;
    }}
    [data-testid="stExpandSidebarButton"] {{
        visibility: visible !important;
        display: flex !important;
        position: fixed !important;
        top: 12px !important;
        left: 12px !important;
        right: auto !important;
        bottom: auto !important;
        z-index: 999998 !important;
        background: var(--primary) !important;
        color: white !important;
        border-radius: 50% !important;
        width: 48px !important;
        height: 48px !important;
        min-width: 48px !important; min-height: 48px !important;
        max-width: 48px !important; max-height: 48px !important;
        box-shadow: var(--shadow-strong) !important;
        border: 2px solid white !important;
        align-items: center !important; justify-content: center !important;
        opacity: 1 !important; transform: none !important;
        margin: 0 !important; padding: 0 !important;
    }}
    [data-testid="stExpandSidebarButton"] * {{
        width: 48px !important; height: 48px !important;
        min-width: 48px !important; min-height: 48px !important;
    }}
    [data-testid="stExpandSidebarButton"] svg {{
        color: white !important; fill: white !important;
        width: 24px !important; height: 24px !important; margin: auto !important;
    }}
    [data-testid="stExpandSidebarButton"]:hover {{
        background: var(--primary-hover) !important;
        transform: scale(1.05) !important;
    }}
    [data-testid="stAppViewBlockContainer"] {{ padding-top: 0.5rem !important; }}
    .main .block-container {{ padding-top: 0.5rem !important; }}
    [data-testid="stSidebar"][aria-expanded="false"] {{
        transform: translateX(-100%) !important;
        margin-left: -21rem !important;
    }}
    [data-testid="stSidebar"] {{
        transition: transform 200ms ease, margin-left 200ms ease !important;
    }}
    .main {{
        margin-left: 0 !important;
        transition: margin-left 200ms ease !important;
    }}
}}

/* === 隱藏 streamlit 內建漢堡按鈕 === */
button[data-testid="stBaseButton-headerNoPadding"] {{
    display: none !important; visibility: hidden !important; pointer-events: none !important;
    width: 0 !important; height: 0 !important; margin: 0 !important; padding: 0 !important;
    border: 0 !important; overflow: hidden !important;
    position: absolute !important; top: -9999px !important; left: -9999px !important;
}}

/* === 浮動漢堡按鈕 === */
#mobile-hamburger-fab {{
    position: fixed;
    top: 12px; left: 12px;
    z-index: 999999;
    width: 44px; height: 44px;
    min-width: 44px; min-height: 44px;
    border-radius: 50%;
    background: var(--primary);
    color: white;
    border: 2px solid white;
    box-shadow: var(--shadow-strong);
    display: flex; align-items: center; justify-content: center;
    cursor: pointer;
    padding: 0; margin: 0; font-size: 0; line-height: 1;
    -webkit-tap-highlight-color: transparent;
    transition: transform 120ms ease, background 120ms ease;
}}
#mobile-hamburger-fab:hover {{
    background: var(--primary-hover);
    transform: scale(1.05);
}}
#mobile-hamburger-fab:active {{ transform: scale(0.95); }}
#mobile-hamburger-fab svg {{
    width: 22px; height: 22px; fill: white; color: white;
}}
@media (min-width: 769px) {{
    #mobile-hamburger-fab {{
        display: flex !important;
        top: 4px; left: 248px;
    }}
    body.sidebar-collapsed #mobile-hamburger-fab {{
        left: 12px !important;
    }}
    [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] {{
        display: none !important; visibility: hidden !important;
    }}
}}
@media (min-width: 769px) {{
    [data-testid="stExpandSidebarButton"] {{display: none;}}
    [data-testid="stToolbar"] {{visibility: hidden;}}
}}

/* === 隱藏 0x0 iframe === */
iframe[height="0"] {{
    display: none !important;
    height: 0 !important; width: 0 !important; border: none !important;
    position: absolute !important; visibility: hidden !important;
}}

/* === Impeccable 風格增強 === */
[data-testid="stSidebar"] h1 {{
    font-size: 0.75rem !important; font-weight: 600 !important;
    color: var(--text-secondary) !important;
    text-transform: uppercase; letter-spacing: 0.08em;
    margin-top: 0 !important; margin-bottom: 10px !important; padding: 0 !important;
}}
[data-testid="stSidebar"] [data-testid="stRadio"] > div {{ gap: 4px !important; }}
[data-testid="stSidebar"] [data-testid="stRadio"] label {{
    padding: 4px 0 !important; font-size: 0.8125rem !important;
}}
[data-testid="stSidebar"] details,
[data-testid="stSidebar"] [data-testid="stExpander"] {{
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    background: var(--bg-card) !important;
    margin-bottom: 6px !important;
}}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
    color: var(--text-muted) !important; font-size: 0.75rem !important;
}}
[data-testid="stSidebar"] [data-baseweb="select"] {{ font-size: 0.8125rem !important; }}
[data-testid="stSidebar"] .stButton button {{
    min-height: 34px !important; padding: 0.4rem 0.75rem !important; font-size: 0.8125rem !important;
}}
[data-testid="stSidebar"] [data-testid="stNumberInput"] input {{
    font-size: 0.8125rem !important; padding: 0.25rem 0.5rem !important;
}}
[data-testid="stSidebar"] [data-testid="stCheckbox"] {{ font-size: 0.8125rem !important; }}

.main h1 {{
    font-size: 1.5rem !important; font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    margin-top: 0.5rem !important; margin-bottom: 0.25rem !important;
}}
.main h2 {{
    font-size: 0.75rem !important; font-weight: 600 !important;
    color: var(--text-secondary) !important;
    text-transform: uppercase !important; letter-spacing: 0.08em !important;
    margin-top: 20px !important; margin-bottom: 10px !important;
}}
.main h3 {{
    font-size: 0.875rem !important; font-weight: 600 !important;
    color: var(--text-secondary) !important;
    text-transform: uppercase !important; letter-spacing: 0.06em !important;
    margin-top: 16px !important; margin-bottom: 8px !important;
}}
.main [data-testid="stCaptionContainer"] {{
    color: var(--text-secondary) !important; font-size: 0.8125rem !important;
    margin-top: 0 !important; margin-bottom: 12px !important;
}}
.stAlert[data-baseweb="notification"] {{
    border-radius: 6px !important; padding: 8px 12px !important; font-size: 0.8125rem !important;
}}
[data-testid="stTextArea"] textarea {{
    font-family: var(--font-mono) !important; font-size: 12.5px !important;
    line-height: 1.55 !important; border-radius: 6px !important;
    background: var(--bg-card) !important; border: 1px solid var(--border) !important;
    padding: 12px 14px !important;
}}
[data-testid="stTextArea"] textarea:focus {{
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.2) !important;
}}
.main [data-testid="stSlider"] {{ padding: 0 !important; }}
.main [data-testid="stDataFrameResizable"] {{
    border: 1px solid var(--border) !important; border-radius: 6px !important;
}}
.main [data-testid="stExpander"] {{
    border: 1px solid var(--border) !important; border-radius: 6px !important;
    background: var(--bg-card) !important; margin-bottom: 8px !important;
}}
.main [data-testid="stProgress"] > div > div {{ background: var(--primary) !important; }}
.main [data-testid="stSpinner"] > div {{
    padding: 4px 0 !important; font-size: 0.875rem !important;
}}
.main .stTabs [aria-selected="true"] {{
    color: var(--primary) !important; font-weight: 600 !important;
    border-bottom: 2px solid var(--primary) !important;
}}
.main .stTabs [data-baseweb="tab"] {{ font-size: 0.875rem !important; }}
.main-header {{
    font-size: 1.5rem !important; font-weight: 700 !important;
    letter-spacing: -0.02em !important; margin-bottom: 4px !important;
}}
.sub-header {{
    font-size: 0.875rem !important; color: var(--text-secondary) !important;
    margin-bottom: 20px !important;
}}
.impeccable-field-label {{
    font-size: 0.6875rem !important; font-weight: 600 !important;
    text-transform: uppercase !important; letter-spacing: 0.08em !important;
    color: var(--text-secondary) !important;
    margin-bottom: 4px !important; display: block;
}}
.impeccable-result-table {{
    width: 100%; border-collapse: collapse;
    font-size: 0.8125rem; font-family: var(--font-mono);
}}
.impeccable-result-table th {{
    text-align: left; font-size: 0.6875rem;
    text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--text-secondary);
    padding: 8px 12px; border-bottom: 1px solid var(--border); font-weight: 600;
}}
.impeccable-result-table td {{
    padding: 8px 12px; border-bottom: 1px solid var(--border);
    color: var(--text-primary);
}}
.impeccable-result-table tr:last-child td {{ border-bottom: none; }}
.impeccable-num-pill {{
    display: inline-block; padding: 1px 8px; border-radius: 4px;
    font-family: var(--font-mono); font-size: 0.75rem; font-weight: 600;
}}
.impeccable-num-pill.success {{ background: var(--green-light); color: var(--green-text); }}
.impeccable-num-pill.error {{ background: var(--red-light); color: var(--red-text); }}
.impeccable-num-pill.neutral {{ background: var(--bg-subtle); color: var(--text-primary); }}

/* === Streamlit selectbox 容器 === */
.stSelectbox [data-baseweb="select"] > div {{
    background: var(--bg-card) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border-strong) !important;
    transition: background-color 250ms ease, color 250ms ease, border-color 150ms ease;
}}
.stSelectbox [data-testid="stSelectbox"] > div:not([class*="react-aria"]) {{
    background: var(--bg-card) !important;
}}
[data-testid="stSelectbox"] .react-aria-ComboBox > div,
[data-testid="stSelectboxVirtual"] .react-aria-ComboBox > div,
[data-testid="stMultiSelect"] .react-aria-ComboBox > div {{
    background: var(--bg-card) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border-strong) !important;
}}
.stSelectbox [data-baseweb="select"] input {{
    color: var(--text-primary) !important;
    caret-color: var(--text-primary) !important;
}}
.stSelectbox [data-baseweb="select"] > div > div {{
    color: var(--text-primary) !important;
}}
.stSelectbox [data-baseweb="select"] svg,
.stSelectbox button svg {{
    fill: var(--text-secondary) !important;
    color: var(--text-secondary) !important;
}}
[data-baseweb="popover"] [data-baseweb="select-option"] {{
    background: var(--bg-card) !important; color: var(--text-primary) !important;
}}
[data-baseweb="popover"] [data-baseweb="select-option"]:hover {{
    background: var(--bg-subtle) !important;
}}
[data-baseweb="popover"] [data-baseweb="select-option"][aria-selected="true"] {{
    background: var(--primary) !important; color: white !important;
}}
.stMultiSelect [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div > div {{
    background: var(--bg-card) !important; color: var(--text-primary) !important;
}}
.stMultiSelect [data-baseweb="select"] svg {{
    fill: var(--text-secondary) !important; color: var(--text-secondary) !important;
}}

.stAlert {{
    border-radius: 6px !important; padding: 8px 14px !important; font-size: 0.8125rem !important;
}}
.stCodeBlock, code, pre {{
    border-radius: 6px !important; font-size: 0.8125rem !important;
    border: 1px solid var(--border) !important;
}}

/* === v5 改進：隱藏 Plotly modebar === */
.plotly .modebar {{ display: none !important; }}
.plotly .modebar-container {{ display: none !important; }}

/* === v7 改進：Plotly 圖表完全用 CSS Variables 同步 === */
/* 圖例文字 */
.plotly .legend text {{
    fill: var(--plotly-text) !important;
    font-weight: 500 !important;
    transition: fill 250ms ease;
}}
.plotly .legend-title {{
    fill: var(--plotly-axis) !important;
}}
/* 軸文字 */
.plotly .xaxislayer-above text, .plotly .yaxislayer-above text,
.plotly .xtick text, .plotly .ytick text {{
    fill: var(--plotly-axis) !important;
    transition: fill 250ms ease;
}}
/* 軸線 */
.plotly .xaxis line, .plotly .yaxis line,
.plotly .xaxis path, .plotly .yaxis path {{
    stroke: var(--plotly-grid) !important;
    transition: stroke 250ms ease;
}}
/* 網格線 */
.plotly .gridlines path {{
    stroke: var(--plotly-grid) !important;
    transition: stroke 250ms ease;
}}
/* Hover 標籤 */
.plotly .hoverlayer .hovertext {{
    fill: var(--bg-card) !important;
    stroke: var(--border) !important;
    transition: fill 250ms ease, stroke 250ms ease;
}}
.plotly .hovertext text {{ fill: var(--plotly-text) !important; }}
.plotly .spikeline {{ stroke: var(--plotly-axis) !important; }}
/* Plotly 圖表背景（用 paper_bgcolor/plot_bgcolor 控制，不強制覆蓋 SVG 內部）*/
/* 不強制改 .main-svg 背景，避免遮蔽 */
.plotly .plot-container .svg-plot .xy .bglayer .bg {{ fill: var(--plotly-plot) !important; }}

/* === 過渡：所有元素都加平滑切換 === */
.stApp, .main .block-container, [data-testid="stSidebar"],
.stButton button, .stTextInput input, .stTextArea textarea,
.stSelectbox [data-baseweb="select"], [data-testid="stMetric"],
.stAlert, .stCodeBlock, code, pre, [data-testid="stExpander"] {{
    transition: background-color 250ms ease, color 250ms ease,
                border-color 250ms ease, box-shadow 250ms ease !important;
}}

/* === 浮動主題切換按鈕 === */
#theme-toggle-fab {{
    position: fixed;
    top: 12px; right: 12px;
    z-index: 999998;
    width: 44px; height: 44px;
    min-width: 44px; min-height: 44px;
    border-radius: 50%;
    background: var(--bg-card);
    color: var(--text-primary);
    border: 1.5px solid var(--border-strong);
    box-shadow: var(--shadow-strong);
    display: flex; align-items: center; justify-content: center;
    cursor: pointer;
    padding: 0; margin: 0; font-size: 0; line-height: 1;
    -webkit-tap-highlight-color: transparent;
    transition: transform 200ms ease, background 200ms ease, border-color 200ms ease, color 200ms ease, box-shadow 200ms ease;
    outline: none !important;
    -webkit-appearance: none !important; appearance: none !important;
}}
#theme-toggle-fab:hover {{
    transform: scale(1.08);
    border-color: var(--primary);
    background: var(--primary);
    color: white;
}}
#theme-toggle-fab:focus, #theme-toggle-fab:focus-visible, #theme-toggle-fab:focus-within {{
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.25), var(--shadow-strong) !important;
}}
#theme-toggle-fab:active {{ transform: scale(0.95); }}
#theme-toggle-fab svg {{
    width: 22px; height: 22px; fill: currentColor; pointer-events: none;
}}
[data-testid="stHeader"] {{ z-index: 999997; }}

/* FAB 旋轉動畫 */
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
    setTimeout(startObserving, 2000);
    var bodyObserver = new MutationObserver(function() {{
        var sidebar = document.querySelector('[data-testid="stSidebar"]');
        if (sidebar && !sidebar._observed) {{
            sidebar._observed = true;
            observer.observe(sidebar, {{ attributes: true, attributeFilter: ['aria-expanded'] }});
            updateSidebarState();
        }}
    }});
    bodyObserver.observe(document.body, {{ childList: true, subtree: true }});
    setInterval(updateSidebarState, 1000);
}})();
</script>
"""
