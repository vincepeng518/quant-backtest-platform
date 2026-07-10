"""
Impeccable 風格輔助元件（第二階段）
- Section header（uppercase + tracking + secondary）
- Stepper / 流程條
- 標籤 + 內容卡片
- 狀態 pill（成功/警告/錯誤/資訊）
- 統一空狀態
"""

from typing import Optional


def section_header(label: str, icon: str = "", theme: dict = None, size: str = "lg") -> str:
    """
    Impeccable 風格的 section header：
    - 11px / 12px / 14px
    - text-transform: uppercase
    - letter-spacing: 0.08em
    - 顏色：text_secondary（次要資訊）
    - 下方一條 1px subtle border
    """
    if theme is None:
        theme = {
            "text_secondary": "#475569",
            "border": "#E2E8F0",
        }
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
        f'color: {theme["text_secondary"]}; '
        f'padding-bottom: {padding}; '
        f'border-bottom: 1px solid {theme["border"]}; '
        f'margin-top: 16px; '
        f'margin-bottom: 12px; '
        f'line-height: 1.4;'
        f'">'
        f'{icon_html}{label}'
        f'</div>'
    )


def step_indicator(steps: list, current: int, theme: dict = None) -> str:
    """
    流程指示器（步驟條）
    steps: ["策略代碼", "執行回測", "檢視結果"]
    current: 0-based 當前步驟
    """
    if theme is None:
        theme = {
            "primary": "#2563EB",
            "border": "#E2E8F0",
            "text_secondary": "#94A3B8",
            "text_primary": "#0F172A",
        }
    items = []
    for i, s in enumerate(steps):
        is_done = i < current
        is_active = i == current
        if is_active:
            color = "white"
            bg = theme["primary"]
            num = str(i + 1)
            text_color = theme["primary"]
        elif is_done:
            color = "white"
            bg = "#22C55E"
            num = "✓"
            text_color = "#22C55E"
        else:
            color = theme["text_secondary"]
            bg = "transparent"
            num = str(i + 1)
            text_color = theme["text_secondary"]
        items.append(
            f'<div style="display: flex; align-items: center; gap: 8px;">'
            f'<div style="width: 24px; height: 24px; border-radius: 50%; '
            f'background: {bg}; color: {color}; display: flex; align-items: center; '
            f'justify-content: center; font-size: 12px; font-weight: 600; '
            f'border: 1px solid {theme["primary"] if is_active else theme["border"]};">'
            f'{num}</div>'
            f'<div style="font-size: 13px; font-weight: {"600" if is_active else "400"}; '
            f'color: {text_color};">{s}</div>'
            f'</div>'
        )
        if i < len(steps) - 1:
            items.append(
                f'<div style="flex: 1; height: 1px; background: {theme["border"]}; '
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
    狀態標籤（pill 形狀）
    status: success / warning / error / info / neutral
    """
    if theme is None:
        theme = {
            "green": "#22C55E",
            "red": "#EF4444",
            "primary": "#2563EB",
            "orange": "#F59E0B",
            "text_secondary": "#94A3B8",
            "green_light": "#DCFCE7",
            "red_light": "#FEE2E2",
            "blue_light": "#DBEAFE",
        }
    config = {
        "success": (theme["green"], theme["green_light"], theme["green_text"] if "green_text" in theme else "#15803D"),
        "warning": (theme["orange"], "#FEF3C7", "#92400E"),
        "error": (theme["red"], theme["red_light"], "#B91C1C"),
        "info": (theme["primary"], theme["blue_light"], "#1E40AF"),
        "neutral": (theme["text_secondary"], "#F1F5F9", theme["text_secondary"]),
    }
    fg, bg, _ = config.get(status, config["info"])
    return (
        f'<span style="display: inline-block; padding: 2px 10px; border-radius: 999px; '
        f'background: {bg}; color: {fg}; font-size: 11px; font-weight: 600; '
        f'letter-spacing: 0.02em; line-height: 1.6;">{text}</span>'
    )


def empty_state(title: str, description: str, icon: str = "📊", theme: dict = None) -> str:
    """
    統一空狀態（取代原本的 st.info + markdown 列表）
    """
    if theme is None:
        theme = {
            "bg_subtle": "#F8FAFC",
            "border": "#E2E8F0",
            "text_primary": "#0F172A",
            "text_secondary": "#475569",
            "primary": "#2563EB",
        }
    return f"""
<div style="
    border: 1px dashed {theme['border']};
    border-radius: 12px;
    padding: 48px 32px;
    text-align: center;
    background: {theme['bg_subtle']};
">
    <div style="font-size: 48px; margin-bottom: 16px; opacity: 0.4;">{icon}</div>
    <div style="font-size: 18px; font-weight: 600; color: {theme['text_primary']};
                margin-bottom: 8px;">{title}</div>
    <div style="font-size: 14px; color: {theme['text_secondary']};
                max-width: 480px; margin: 0 auto;">{description}</div>
</div>
"""


def metric_row(items: list, theme: dict = None) -> str:
    """
    一列 N 個小指標（KPI 風格，比 st.metric 更緊湊）
    items: [{"label": "目標值", "value": "0.85", "color": "primary"}, ...]
    """
    if theme is None:
        theme = {
            "bg_card": "#FFFFFF",
            "border": "#E2E8F0",
            "text_secondary": "#94A3B8",
            "text_primary": "#0F172A",
            "primary": "#2563EB",
            "green": "#22C55E",
            "red": "#EF4444",
            "orange": "#F59E0B",
            "font_mono": "'JetBrains Mono', monospace",
        }
    cells = []
    for item in items:
        color = item.get("color", "primary")
        color_map = {
            "primary": theme["primary"],
            "success": theme["green"],
            "error": theme["red"],
            "warning": theme["orange"],
        }
        fg = color_map.get(color, theme["primary"])
        cells.append(
            f'<div style="flex: 1; padding: 12px 16px; '
            f'background: {theme["bg_card"]}; border: 1px solid {theme["border"]}; '
            f'border-radius: 6px;">'
            f'<div style="font-size: 11px; font-weight: 600; text-transform: uppercase; '
            f'letter-spacing: 0.06em; color: {theme["text_secondary"]}; '
            f'margin-bottom: 4px;">{item["label"]}</div>'
            f'<div style="font-size: 18px; font-weight: 600; color: {fg}; '
            f'font-family: {theme["font_mono"]};">{item["value"]}</div>'
            f'</div>'
        )
    return (
        f'<div style="display: flex; gap: 8px; margin: 8px 0 16px 0;">'
        + "".join(cells) +
        f'</div>'
    )


def info_card(title: str, body: str, theme: dict = None, accent: str = "primary") -> str:
    """
    Impeccable 資訊卡（左側色條）
    accent: primary / success / warning / error
    """
    if theme is None:
        theme = {
            "bg_card": "#FFFFFF",
            "bg_subtle": "#F8FAFC",
            "border": "#E2E8F0",
            "text_primary": "#0F172A",
            "text_secondary": "#475569",
            "primary": "#2563EB",
            "green": "#22C55E",
            "red": "#EF4444",
            "orange": "#F59E0B",
        }
    accent_map = {
        "primary": theme["primary"],
        "success": theme["green"],
        "warning": theme["orange"],
        "error": theme["red"],
    }
    bar = accent_map.get(accent, theme["primary"])
    return f"""
<div style="
    background: {theme['bg_subtle']};
    border: 1px solid {theme['border']};
    border-left: 3px solid {bar};
    border-radius: 6px;
    padding: 12px 16px;
    margin: 8px 0;
">
    <div style="font-size: 13px; font-weight: 600; color: {theme['text_primary']};
                margin-bottom: 4px;">{title}</div>
    <div style="font-size: 12px; color: {theme['text_secondary']};
                line-height: 1.5;">{body}</div>
</div>
"""
