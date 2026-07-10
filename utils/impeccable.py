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
