"""
Impeccable 風格輔助元件（v7：CSS Variables 同步主題切換）

設計改進：
- 顏色用 var(--xxx) 引用 CSS variables（不是 hex）
- 切換 data-theme 屬性時，自動跟著變色
- 不再依賴 Python 端傳入的 theme dict
"""

from typing import Optional


def section_header(label: str, icon: str = "", theme: dict = None, size: str = "lg") -> str:
    """
    Impeccable 風格的 section header（v7：用 CSS variables）。
    """
    sizes = {
        "sm": ("11px", "12px"),
        "md": ("12px", "16px"),
        "lg": ("13px", "20px"),
    }
    font_size, padding = sizes.get(size, sizes["lg"])
    icon_html = f'<span style="margin-right: 6px;">{icon}</span>' if icon else ""
    return (
        f'<div style="'
        f'font-size: {font_size}; '
        f'font-weight: 600; '
        f'text-transform: uppercase; '
        f'letter-spacing: 0.08em; '
        f'color: var(--text-secondary); '
        f'padding-bottom: {padding}; '
        f'border-bottom: 1px solid var(--border); '
        f'margin-top: 16px; '
        f'margin-bottom: 12px; '
        f'line-height: 1.4;'
        f'">'
        f'{icon_html}{label}'
        f'</div>'
    )


def step_indicator(steps: list, current: int, theme: dict = None) -> str:
    """
    流程指示器（步驟條，v7：用 CSS variables）。
    """
    items = []
    for i, s in enumerate(steps):
        is_done = i < current
        is_active = i == current
        if is_active:
            # 當前步驟：藍底白字
            bg = "var(--primary)"
            color = "white"
            num = str(i + 1)
            text_color = "var(--primary)"
            border = "var(--primary)"
        elif is_done:
            # 已完成：綠底白字
            bg = "var(--green)"
            color = "white"
            num = "✓"
            text_color = "var(--green-text)"
            border = "var(--green)"
        else:
            # 未完成：透明
            bg = "transparent"
            color = "var(--text-muted)"
            num = str(i + 1)
            text_color = "var(--text-secondary)"
            border = "var(--border)"
        items.append(
            f'<div style="display: flex; align-items: center; gap: 8px;">'
            f'<div style="width: 24px; height: 24px; border-radius: 50%; '
            f'background: {bg}; color: {color}; display: flex; align-items: center; '
            f'justify-content: center; font-size: 12px; font-weight: 600; '
            f'border: 1px solid {border};">'
            f'{num}</div>'
            f'<div style="font-size: 13px; font-weight: {"600" if is_active else "400"}; '
            f'color: {text_color};">{s}</div>'
            f'</div>'
        )
        if i < len(steps) - 1:
            items.append(
                f'<div style="flex: 1; height: 1px; background: var(--border); '
                f'margin: 0 8px; min-width: 20px;"></div>'
            )
    return (
        f'<div style="display: flex; align-items: center; padding: 8px 0 16px 0; '
        f'gap: 4px;">'
        + "".join(items) +
        f'</div>'
    )


def status_pill(text: str, status: str = "info", theme: dict = None) -> str:
    """
    狀態標籤（pill 形狀，v7：用 CSS variables）。
    """
    config = {
        "success": ("var(--green-text)", "var(--green-light)"),
        "warning": ("#92400E", "#FEF3C7"),
        "error": ("var(--red-text)", "var(--red-light)"),
        "info": ("#1E40AF", "#DBEAFE"),
        "neutral": ("var(--text-secondary)", "var(--bg-subtle)"),
    }
    fg, bg = config.get(status, config["info"])
    return (
        f'<span style="display: inline-block; padding: 2px 10px; border-radius: 999px; '
        f'background: {bg}; color: {fg}; font-size: 11px; font-weight: 600; '
        f'letter-spacing: 0.02em; line-height: 1.6;">{text}</span>'
    )


def empty_state(title: str, description: str, icon: str = "📊", theme: dict = None) -> str:
    """
    統一空狀態（v7：用 CSS variables）。
    """
    return f"""
<div style="
    border: 1px dashed var(--border);
    border-radius: 12px;
    padding: 48px 32px;
    text-align: center;
    background: var(--bg-subtle);
">
    <div style="font-size: 48px; margin-bottom: 16px; opacity: 0.4;">{icon}</div>
    <div style="font-size: 18px; font-weight: 600; color: var(--text-primary);
                margin-bottom: 8px;">{title}</div>
    <div style="font-size: 14px; color: var(--text-secondary);
                max-width: 480px; margin: 0 auto;">{description}</div>
</div>
"""


def welcome_panel(theme: dict = None) -> str:
    """v9 改進：質感化的中央歡迎 + 操作指引面板。

    設計：
    - 大型漸層 hero 區塊（藍色 primary 漸層到 bg）
    - 醒目的標題與副標題
    - 3 步驟引導卡（側邊欄 → 載入 → 回測）
    - 內建策略範本標籤雲
    - 「快速提示」底部區塊

    v10 改進：完全改用 string concatenation 而非 f-string，避免 f-string 內
    大段 CSS 導致 streamlit markdown 解析器在某些版本把整段當純文字。

    用法（推薦 streamlit 1.59+）：
        st.html(welcome_panel(theme=current_theme))
    備援（streamlit <1.59）：
        st.markdown(welcome_panel(theme=current_theme), unsafe_allow_html=True)
    """
    t = theme or {}
    primary = t.get("primary", "#2962FF")
    primary_hover = t.get("primary_hover", "#1E53E5")
    text_primary = t.get("text_primary", "#0F172A")
    text_secondary = t.get("text_secondary", "#64748B")
    text_muted = t.get("text_muted", "#94A3B8")
    bg_card = t.get("bg_card", "#FFFFFF")
    bg_subtle = t.get("bg_subtle", "#F8FAFC")
    border = t.get("border", "#E2E8F0")
    border_strong = t.get("border_strong", "#CBD5E1")

    return (
        '<div style="border: 1px solid ' + border + '; border-radius: 16px;'
        'background: linear-gradient(135deg, ' + primary + '11 0%, ' + bg_card + ' 60%, ' + bg_subtle + ' 100%);'
        'padding: 0; margin: 16px 0 24px 0; overflow: hidden;'
        'box-shadow: 0 1px 3px rgba(0,0,0,0.04);">'
        # Hero
        + '<div style="background: linear-gradient(135deg, ' + primary + ' 0%, ' + primary_hover + ' 100%);'
        'padding: 32px 36px 28px 36px; color: white;">'
        '<div style="font-size: 12px; font-weight: 600; letter-spacing: 0.12em;'
        'text-transform: uppercase; opacity: 0.85; margin-bottom: 6px;">'
        'WELCOME TO CRYPTO BACKTESTING LAB</div>'
        '<div style="font-size: 26px; font-weight: 700; line-height: 1.25;'
        'margin-bottom: 8px; letter-spacing: -0.01em;">'
        '從左側邊欄開始你的回測旅程</div>'
        '<div style="font-size: 14px; opacity: 0.92; line-height: 1.5; max-width: 560px;">'
        '選擇資料來源、設定策略參數，一鍵執行回測，獲得完整的交易報告與圖表分析。</div>'
        '</div>'
        # 3 步驟引導卡（用 flex 而非 grid，相容性更好）
        + '<div style="display: flex; gap: 0; padding: 24px 36px 8px 36px;">'
        + '<div style="flex: 1; padding: 4px 20px 4px 0; border-right: 1px solid ' + border + ';">'
        '<div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">'
        '<div style="width: 28px; height: 28px; border-radius: 50%;'
        'background: ' + primary + '; color: white;'
        'display: flex; align-items: center; justify-content: center;'
        'font-size: 14px; font-weight: 700;">1</div>'
        '<div style="font-size: 14px; font-weight: 600; color: ' + text_primary + ';">選擇資料</div>'
        '</div>'
        '<div style="font-size: 13px; color: ' + text_secondary + '; line-height: 1.55;">'
        '從左側邊欄選擇「加密貨幣 / CSV / 配對交易」任一來源。</div>'
        '</div>'
        + '<div style="flex: 1; padding: 4px 20px; border-right: 1px solid ' + border + ';">'
        '<div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">'
        '<div style="width: 28px; height: 28px; border-radius: 50%;'
        'background: ' + primary + '; color: white;'
        'display: flex; align-items: center; justify-content: center;'
        'font-size: 14px; font-weight: 700;">2</div>'
        '<div style="font-size: 14px; font-weight: 600; color: ' + text_primary + ';">載入資料</div>'
        '</div>'
        '<div style="font-size: 13px; color: ' + text_secondary + '; line-height: 1.55;">'
        '按「<b style="color:' + text_primary + '">一鍵測試資料</b>」用 500 根模擬 K 線立刻體驗，'
        '或從交易所抓取真實歷史資料。</div>'
        '</div>'
        + '<div style="flex: 1; padding: 4px 0 4px 20px;">'
        '<div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">'
        '<div style="width: 28px; height: 28px; border-radius: 50%;'
        'background: ' + primary + '; color: white;'
        'display: flex; align-items: center; justify-content: center;'
        'font-size: 14px; font-weight: 700;">3</div>'
        '<div style="font-size: 14px; font-weight: 600; color: ' + text_primary + ';">執行回測</div>'
        '</div>'
        '<div style="font-size: 13px; color: ' + text_secondary + '; line-height: 1.55;">'
        '選擇策略、調整參數，按「▶️ 執行回測」獲得完整報告。</div>'
        '</div>'
        + '</div>'
        # 內建策略範本標籤雲
        + '<div style="padding: 18px 36px 8px 36px; border-top: 1px solid ' + border + '; margin-top: 16px;">'
        '<div style="font-size: 11px; font-weight: 600; color: ' + text_muted + '; letter-spacing: 0.08em;'
        'text-transform: uppercase; margin-bottom: 10px;">內建策略範本</div>'
        '<div style="display: flex; flex-wrap: wrap; gap: 6px;">'
        + '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">SMA 交叉</span>'
        '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">RSI</span>'
        '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">布林通道</span>'
        '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">MACD</span>'
        '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">網格交易</span>'
        '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">海龜</span>'
        '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">KDJ</span>'
        '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">CCI</span>'
        '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">Donchian</span>'
        '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">TEMA</span>'
        '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">VWAP</span>'
        '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">OBV</span>'
        '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">一目均衡表</span>'
        '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">Parabolic SAR</span>'
        '<span style="padding: 4px 10px; border-radius: 999px; background: ' + bg_subtle + '; color: ' + text_secondary + '; font-size: 12px; font-weight: 500;">BTC/ETH 比率配對</span>'
        + '</div>'
        '</div>'
        # 底部提示
        + '<div style="padding: 14px 36px 16px 36px; background: ' + bg_subtle + ';'
        'color: ' + text_secondary + '; font-size: 12px; display: flex;'
        'align-items: center; gap: 8px;">'
        '<span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%;'
        'background: ' + primary + ';"></span>'
        '<span><b style="color:' + text_primary + '">快速提示：</b>最簡單的方式 — 在左側選擇「加密貨幣」資料源後，直接點「<b>一鍵測試資料</b>」即可立刻體驗完整回測流程。</span>'
        '</div>'
        # 容器關閉
        + '</div>'
    )


def metric_row(items: list, theme: dict = None) -> str:
    """
    一列 N 個小指標（v7：用 CSS variables）。
    items: [{"label": "目標值", "value": "0.85", "color": "primary"}, ...]
    """
    cells = []
    for item in items:
        color = item.get("color", "primary")
        # 用 var()，但 var(--primary-hover) 等不存在時 fallback 到 var(--primary)
        color_map = {
            "primary": "var(--primary)",
            "success": "var(--green-text)",
            "error": "var(--red-text)",
            "warning": "var(--orange)",
        }
        fg = color_map.get(color, "var(--primary)")
        cells.append(
            f'<div style="flex: 1; padding: 12px 16px; '
            f'background: var(--bg-card); border: 1px solid var(--border); '
            f'border-radius: 6px;">'
            f'<div style="font-size: 11px; font-weight: 600; text-transform: uppercase; '
            f'letter-spacing: 0.06em; color: var(--text-secondary); '
            f'margin-bottom: 4px;">{item["label"]}</div>'
            f'<div style="font-size: 18px; font-weight: 600; color: {fg}; '
            f'font-family: var(--font-mono);">{item["value"]}</div>'
            f'</div>'
        )
    return (
        f'<div style="display: flex; gap: 8px; margin: 8px 0 16px 0;">'
        + "".join(cells) +
        f'</div>'
    )


def info_card(title: str, body: str, theme: dict = None, accent: str = "primary") -> str:
    """
    Impeccable 資訊卡（左側色條，v7：用 CSS variables）。
    """
    accent_map = {
        "primary": "var(--primary)",
        "success": "var(--green-text)",
        "warning": "var(--orange)",
        "error": "var(--red-text)",
    }
    bar = accent_map.get(accent, "var(--primary)")
    return f"""
<div style="
    background: var(--bg-subtle);
    border: 1px solid var(--border);
    border-left: 3px solid {bar};
    border-radius: 6px;
    padding: 12px 16px;
    margin: 8px 0;
">
    <div style="font-size: 13px; font-weight: 600; color: var(--text-primary);
                margin-bottom: 4px;">{title}</div>
    <div style="font-size: 12px; color: var(--text-secondary);
                line-height: 1.5;">{body}</div>
</div>
"""
