"""
回測結果 UI 元件 — TradingView 專業風格（第一階段重設計）

設計原則：
- 借鑑 TradingView 圖表頁的版式：上方 KPI 卡片列 + 主圖 + 子圖 + 互動
- 保留現有兩個主題（Light Pro / Dark Trading），但強化深色模式的 TV 風格
- KPI 卡片用 monospace 字體 + 細 1px border + subtle 陰影（克制原則）
- 主圖用 Plotly：可縮放、平移、十字線懸停統一顯示
- 子圖（Drawdown）用 fill area，避免 AI-slop 紫色漸變

色板：
- 綠色（獲利/Buy）：#22C55E / #4ADE80
- 紅色（虧損/Sell）：#EF4444 / #F87171
- Buy & Hold 基準：#F59E0B（橙色，避免與綠紅混淆）
- 強調色：theme.primary（藍色）
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Dict, List, Any, Optional

from utils.theme import get_current_theme


# === Impeccable: 計算衍生指標（不重複定義） ===
def calc_calmar_ratio(total_return_pct: float, max_drawdown_pct: float) -> float:
    if max_drawdown_pct == 0:
        return 0
    return total_return_pct / abs(max_drawdown_pct)


def calc_sortino_ratio(returns: pd.Series, risk_free: float = 0) -> float:
    downside = returns[returns < 0]
    if len(downside) == 0 or downside.std() == 0:
        return 0
    excess = returns - risk_free
    return (excess.mean() / downside.std()) * np.sqrt(252)


def calc_recovery_factor(total_return_pct: float, max_drawdown_pct: float) -> float:
    if max_drawdown_pct == 0:
        return 0
    return total_return_pct / abs(max_drawdown_pct)


def calc_avg_win_loss_ratio(avg_win: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 0
    return abs(avg_win / avg_loss)


def calc_expectancy(win_rate: float, avg_win: float, avg_loss: float) -> float:
    return (win_rate / 100) * avg_win - (1 - win_rate / 100) * abs(avg_loss)


def calc_cagr(equity: pd.Series, periods_per_year: int = 252) -> float:
    """年化報酬率（CAGR）。"""
    if len(equity) < 2 or equity.iloc[0] <= 0 or equity.iloc[-1] <= 0:
        return 0
    n_periods = len(equity)
    years = n_periods / periods_per_year
    if years <= 0:
        return 0
    return ((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1) * 100


def calc_alpha(strategy_return: float, buy_hold_return: float) -> float:
    """超額報酬 = 策略 - Buy & Hold。"""
    return strategy_return - buy_hold_return


# === 顏色輔助（從 theme 動態讀）===
def _palette() -> Dict[str, str]:
    t = get_current_theme()
    return {
        # 向下相容：保留 'bg' 別名
        "bg": t.get("bg") or t.get("bg_primary", "#131722"),
        "bg_primary": t.get("bg_primary", "#131722"),
        "bg_subtle": t["bg_subtle"],
        "bg_card": t["bg_card"],
        "border": t["border"],
        "border_strong": t["border_strong"],
        "text_primary": t["text_primary"],
        "text_secondary": t["text_secondary"],
        "text_muted": t["text_muted"],
        "primary": t["primary"],
        "primary_hover": t.get("primary_hover", t["primary"]),
        "green": t["green"],
        "green_light": t["green_light"],
        "green_text": t["green_text"],
        "red": t["red"],
        "red_light": t["red_light"],
        "red_text": t["red_text"],
        "orange": t["orange"],
        "yellow": t["yellow"],
        "purple": t["purple"],
        "font_family": t["font_family"],
        "font_mono": t["font_mono"],
        "shadow": t.get("shadow", "none"),
        "shadow_strong": t.get("shadow_strong", t.get("shadow", "none")),
        "radius": t.get("radius", "8px"),
    }


# === TradingView 風格 KPI 卡片列 ===
def _kpi_card_html(
    label: str,
    value: str,
    sentiment: str = "neutral",  # 'positive' | 'negative' | 'neutral'
    sub: str = "",
) -> str:
    """單個 KPI 卡（Impeccable 風格：緊湊、border-only、右對齊）。"""
    p = _palette()
    if sentiment == "positive":
        accent = p["green_text"]
    elif sentiment == "negative":
        accent = p["red_text"]
    else:
        accent = p["text_primary"]

    sub_block = ""
    if sub:
        sub_color = p["text_muted"]
        if sub.startswith("+"):
            sub_color = p["green_text"]
        elif sub.startswith("-"):
            sub_color = p["red_text"]
        sub_block = (
            '<div style="color: ' + sub_color + '; font-size: 10px; margin-top: 2px; font-weight: 500; '
            'font-family: ' + p["font_mono"] + '; text-align: right;">'
            + sub +
            '</div>'
        )

    card_html = (
        '<div style="'
        'background: ' + p["bg_card"] + '; '
        'border: 1px solid ' + p["border"] + '; '
        'border-radius: 5px; '
        'padding: 8px 12px; '
        'min-height: 58px; '
        'display: flex; '
        'flex-direction: column; '
        'justify-content: center;'
        '">'
        '<div style="'
        'color: ' + p["text_secondary"] + '; '
        'font-size: 10px; '
        'font-weight: 700; '
        'text-align: left;'
        '">' + label + '</div>'
        '<div style="margin-top: 4px; text-align: right;">'
        '<div style="'
        'color: ' + accent + '; '
        'font-family: ' + p["font_mono"] + '; '
        'font-size: 20px; '
        'font-weight: 600; '
        'line-height: 1.15; '
        'text-align: right;'
        '">' + value + '</div>'
        + sub_block +
        '</div>'
        '</div>'
    )
    return card_html


def render_kpi_cards(metrics: Dict, result_df: pd.DataFrame) -> None:
    """TradingView 風格的 KPI 卡片列（12 個關鍵指標）。"""
    p = _palette()
    initial_capital = metrics.get("initial_capital", 10000)
    total_return = metrics.get("total_return_pct", 0)
    final_equity = metrics.get("final_equity", initial_capital)
    net_profit = final_equity - initial_capital
    max_dd = metrics.get("max_drawdown_pct", 0)
    win_rate = metrics.get("win_rate", 0)
    n_trades = metrics.get("n_trades", 0)
    sharpe = metrics.get("sharpe_ratio", 0)
    profit_factor = metrics.get("profit_factor", 0)
    buy_hold = metrics.get("buy_hold_return_pct", 0)
    avg_win = metrics.get("avg_win_pct", 0)
    avg_loss = metrics.get("avg_loss_pct", 0)
    returns = result_df["strategy_returns"].dropna() if "strategy_returns" in result_df.columns else pd.Series()
    sortino = calc_sortino_ratio(returns) if len(returns) > 0 else 0
    calmar = calc_calmar_ratio(total_return, max_dd)

    # 計算 CAGR：用 strategy_returns 頻率推斷
    periods_per_year = 252
    if "equity" in result_df.columns and len(result_df) > 1:
        try:
            if isinstance(result_df.index, pd.DatetimeIndex):
                median_diff = result_df.index.to_series().diff().median().total_seconds()
                if median_diff <= 60:
                    periods_per_year = 252 * 24 * 60
                elif median_diff <= 3600:
                    periods_per_year = 252 * 24
                elif median_diff <= 86400:
                    periods_per_year = 252
                elif median_diff <= 86400 * 7:
                    periods_per_year = 52
                else:
                    periods_per_year = 12
        except Exception:
            periods_per_year = 252
    cagr = calc_cagr(result_df["equity"], periods_per_year) if "equity" in result_df.columns else total_return
    alpha = calc_alpha(total_return, buy_hold)

    # 第 1 列：主要 KPI（6 張）
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.markdown(_kpi_card_html(
            "淨利潤", f"${net_profit:+,.0f}",
            "positive" if net_profit >= 0 else "negative",
        ), unsafe_allow_html=True)
    with c2:
        st.markdown(_kpi_card_html(
            "總報酬", f"{total_return:+.2f}%",
            "positive" if total_return >= 0 else "negative",
            sub=f"vs Buy &amp; Hold {buy_hold:+.2f}%" if buy_hold else "",
        ), unsafe_allow_html=True)
    with c3:
        st.markdown(_kpi_card_html(
            "CAGR", f"{cagr:+.2f}%",
            "positive" if cagr >= 0 else "negative",
        ), unsafe_allow_html=True)
    with c4:
        st.markdown(_kpi_card_html(
            "最大回撤", f"{max_dd:.2f}%",
            "negative" if abs(max_dd) > 20 else ("neutral" if abs(max_dd) > 10 else "positive"),
        ), unsafe_allow_html=True)
    with c5:
        st.markdown(_kpi_card_html(
            "Sharpe", f"{sharpe:.2f}",
            "positive" if sharpe > 1 else ("neutral" if sharpe > 0 else "negative"),
        ), unsafe_allow_html=True)
    with c6:
        st.markdown(_kpi_card_html(
            "Calmar", f"{calmar:.2f}",
            "positive" if calmar > 1 else ("neutral" if calmar > 0 else "negative"),
        ), unsafe_allow_html=True)

    # 第 2 列：交易 KPI（6 張）
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.markdown(_kpi_card_html(
            "勝率", f"{win_rate:.1f}%",
            "positive" if win_rate >= 50 else "negative",
            sub=f"{n_trades} 筆交易",
        ), unsafe_allow_html=True)
    with c2:
        st.markdown(_kpi_card_html(
            "Profit Factor", f"{profit_factor:.2f}" if np.isfinite(profit_factor) else "∞",
            "positive" if profit_factor > 1.5 else ("neutral" if profit_factor > 1 else "negative"),
        ), unsafe_allow_html=True)
    with c3:
        st.markdown(_kpi_card_html(
            "Sortino", f"{sortino:.2f}",
            "positive" if sortino > 1 else ("neutral" if sortino > 0 else "negative"),
        ), unsafe_allow_html=True)
    with c4:
        st.markdown(_kpi_card_html(
            "風報比", f"{abs(avg_win/avg_loss):.2f}" if avg_loss != 0 else "∞",
            "positive" if abs(avg_win) > abs(avg_loss) else "negative",
        ), unsafe_allow_html=True)
    with c5:
        st.markdown(_kpi_card_html(
            "α 超額報酬", f"{alpha:+.2f}%",
            "positive" if alpha > 0 else "negative",
        ), unsafe_allow_html=True)
    with c6:
        st.markdown(_kpi_card_html(
            "最終權益", f"${final_equity:,.0f}",
            "positive" if final_equity >= initial_capital else "negative",
        ), unsafe_allow_html=True)


# === TradingView 風格主圖：權益曲線 + Buy &amp; Hold + Drawdown ===
def render_equity_chart(result_df: pd.DataFrame, metrics: Dict) -> None:
    """TradingView 風格權益曲線（主圖）+ Drawdown（子圖）。"""
    p = _palette()
    initial_capital = metrics.get("initial_capital", 10000)
    net_profit = metrics.get("final_equity", initial_capital) - initial_capital
    is_profit = net_profit >= 0

    equity_color = p["green"] if is_profit else p["red"]
    fill_rgba = "rgba(34, 197, 94, 0.08)" if is_profit else "rgba(239, 68, 68, 0.08)"

    # Drawdown 計算
    equity = result_df["equity"]
    cummax = equity.cummax()
    drawdown_pct = (equity - cummax) / cummax * 100

    # 雙子圖（主圖 65% + Drawdown 35%）
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.65, 0.35],
        subplot_titles=("", "回撤"),
    )

    # 主圖：策略權益（fill area）
    fig.add_trace(
        go.Scatter(
            x=result_df.index,
            y=result_df["equity"],
            name="策略權益",
            mode="lines",
            line=dict(color=equity_color, width=2),
            fill="tozeroy",
            fillcolor=fill_rgba,
            hovertemplate="<b>%{x|%Y-%m-%d %H:%M}</b><br>策略權益: $%{y:,.2f}<extra></extra>",
        ),
        row=1, col=1,
    )

    # Buy & Hold 基準
    if "buy_hold" in result_df.columns:
        fig.add_trace(
            go.Scatter(
                x=result_df.index,
                y=result_df["buy_hold"],
                name="Buy & Hold",
                mode="lines",
                line=dict(color=p["orange"], width=1.5, dash="dash"),
                opacity=0.8,
                hovertemplate="<b>%{x|%Y-%m-%d %H:%M}</b><br>Buy & Hold: $%{y:,.2f}<extra></extra>",
            ),
            row=1, col=1,
        )

    # Drawdown 子圖
    fig.add_trace(
        go.Scatter(
            x=result_df.index,
            y=drawdown_pct,
            name="回撤",
            mode="lines",
            line=dict(color=p["red"], width=1),
            fill="tozeroy",
            fillcolor="rgba(239, 68, 68, 0.15)",
            hovertemplate="<b>%{x|%Y-%m-%d %H:%M}</b><br>回撤: %{y:.2f}%<extra></extra>",
        ),
        row=2, col=1,
    )

    # Layout
    fig.update_layout(
        height=560,
        hovermode="x unified",
        template=get_current_theme()["plotly_template"],
        paper_bgcolor=p["bg"],
        plot_bgcolor=p["bg"],
        font=dict(color=p["text_primary"], family="system-ui", size=12),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(0,0,0,0)",
            borderwidth=0,
            font=dict(size=12),
        ),
        hoverlabel=dict(
            bgcolor="rgba(28, 31, 42, 0.9)",
            bordercolor="rgba(80, 85, 100, 0.3)",
            font=dict(color="#FFFFFF", size=12),
            align="left",
            namelength=-1,
        ),
        margin=dict(l=60, r=16, t=24, b=36),
        xaxis=dict(gridcolor=p["border"], showgrid=True, zeroline=False, rangeslider=dict(visible=False), gridwidth=1, griddash="dot"),
        xaxis2=dict(gridcolor=p["border"], showgrid=False, zeroline=False, griddash="dot"),
        yaxis=dict(
            gridcolor=p["border"],
            showgrid=True,
            zeroline=False,
            title=dict(text="權益 (USDT)", font=dict(size=11, color=p["text_secondary"])),
            side="left",
            gridwidth=1,
            griddash="dot",
        ),
        yaxis2=dict(
            gridcolor=p["border"],
            showgrid=True,
            zeroline=False,
            title=dict(text="回撤 (%)", font=dict(size=11, color=p["text_secondary"])),
            side="left",
            gridwidth=1,
            griddash="dot",
        ),
    )

    # X 軸時間格式
    try:
        if isinstance(result_df.index, pd.DatetimeIndex):
            median_diff = result_df.index.to_series().diff().median().total_seconds()
            if median_diff <= 86400:
                fig.update_xaxes(tickformat="%m-%d")
            else:
                fig.update_xaxes(tickformat="%Y-%m")
    except Exception:
        pass

    st.plotly_chart(fig, use_container_width=True, config={"staticPlot": True, "displayModeBar": False})


def _tv_kpi_card_html(
    label: str,
    value: str,
    sub: str = "",
    sub_color: str = None,
    icon_svg: str = "",
    tooltip: str = "",
) -> str:
    """TradingView 風格單個 KPI 卡（Impeccable 重構：緊湊、border-only、右對齊）。

    設計：
    - 標題 10px 粗體灰（不 uppercase, 不 tracking）
    - 數值 20px monospace（右對齊）
    - 副標題 10px
    - padding 8px 12px, border 1px, radius 5px
    - 無 shadow，用 border 區分層級
    - 右上角 SVG 圓圈問號 tooltip icon（可選）
    """
    p = _palette()
    if sub_color is None:
        sub_color = p["text_muted"]

    # SVG ⓘ icon
    info_icon = ""
    if tooltip:
        tooltip_escaped = tooltip.replace('"', '&quot;').replace("'", "&#39;")
        info_icon = (
            '<span style="display: inline-flex; align-items: center; justify-content: center; '
            'width: 13px; height: 13px; border-radius: 50%; border: 1px solid ' + p["text_muted"] + '; '
            'color: ' + p["text_muted"] + '; margin-left: 6px; cursor: help; font-size: 9px; '
            'font-weight: 700; line-height: 1; vertical-align: middle;" '
            'title="' + tooltip_escaped + '">i</span>'
        )
    sub_block = ""
    if sub:
        sub_block = (
            '<div style="color: ' + sub_color + '; font-size: 10px; margin-top: 2px; font-weight: 500; '
            'font-family: ' + p["font_mono"] + '; text-align: right;">'
            + sub + '</div>'
        )
    # 主卡片結構（Impeccable：緊湊、border-only、右對齊數值）
    return (
        '<div style="'
        'background: ' + p["bg_card"] + '; '
        'border: 1px solid ' + p["border"] + '; '
        'border-radius: 5px; '
        'padding: 8px 12px; '
        'min-height: 58px; '
        'display: flex; '
        'flex-direction: column; '
        'justify-content: center;'
        '">'
        '<div style="'
        'color: ' + p["text_secondary"] + '; '
        'font-size: 10px; '
        'font-weight: 700; '
        'display: flex; '
        'align-items: center; '
        '">'
        '<span>' + label + '</span>'
        + info_icon +
        '</div>'
        '<div style="'
        'color: ' + p["text_primary"] + '; '
        'font-family: ' + p["font_mono"] + '; '
        'font-size: 20px; '
        'font-weight: 600; '
        'line-height: 1.15; '
        'margin-top: 4px; '
        'text-align: right;'
        '">' + value + '</div>'
        + sub_block +
        '</div>'
    )


def render_tv_overview(
    metrics: Dict,
    result_df: pd.DataFrame,
    initial_capital: float,
    trades: Optional[List[Dict]] = None,
) -> None:
    """TradingView Strategy Tester 風格的 Overview 頁面。

    結構（與截圖一致）：
    ┌─ Strategy Backtest Report 標題列（含 Buy & Hold toggle、Absolute/Percent toggle）┐
    ├─ 5 大核心 KPI 卡片列（Total P&L / Max Drawdown / Total Trades / Profitable / Profit Factor）┤
    ├─ 6 個次要 KPI 卡片列（Buy & Hold / Sharpe / Calmar / CAGR / Sortino / Recovery）┤
    ├─ 主圖：權益曲線 + Buy & Hold + Drawdown 子圖┤
    ├─ 交易統計 4×3 網格 KPI┤

    參數：
        trades: 交易明細 list[dict]，用於統一計算 n_wins / win_rate
                （確保「獲利筆數 / 總筆數 = 勝率」永遠一致）
                若未提供則 fallback 到 metrics（向後相容）
    """
    p = _palette()

    # === 數據準備 ===
    metrics_with_cap = {**metrics, "initial_capital": initial_capital}
    total_return = metrics.get("total_return_pct", 0)
    final_equity = metrics.get("final_equity", initial_capital)
    net_profit = final_equity - initial_capital
    max_dd = metrics.get("max_drawdown_pct", 0)
    max_dd_amount = initial_capital * abs(max_dd) / 100 if max_dd else 0

    # 統一來源：n_wins / win_rate / n_trades 一律用 trades 實際計算
    # 確保「獲利交易筆數 / 總交易筆數 = 勝率」永遠一致
    # 之前用 metrics.win_rate × n_trades 反推 n_wins 會在 win_rate 計算錯誤時
    # 導致「顯示 1/6 但勝率 33.33%」這種不一致問題
    from utils.trade_stats import compute_trade_stats
    _stats = compute_trade_stats(result_df=result_df, trades=trades, metrics=metrics)
    n_trades = int(_stats.get("n_trades", 0))
    n_wins = int(_stats.get("n_wins", 0))
    win_rate = float(_stats.get("win_rate", 0.0))  # 已經是 0-100 的百分比

    sharpe = metrics.get("sharpe_ratio", 0)
    profit_factor = metrics.get("profit_factor", 0)
    buy_hold = metrics.get("buy_hold_return_pct", 0)
    avg_win = metrics.get("avg_win_pct", 0)
    avg_loss = metrics.get("avg_loss_pct", 0)

    returns = (
        result_df["strategy_returns"].dropna()
        if "strategy_returns" in result_df.columns
        else pd.Series()
    )
    sortino = calc_sortino_ratio(returns) if len(returns) > 0 else 0
    calmar = calc_calmar_ratio(total_return, max_dd)
    recovery = calc_recovery_factor(total_return, max_dd)
    rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0

    # CAGR 計算（從時間頻率推斷）
    periods_per_year = 252
    if (
        "equity" in result_df.columns
        and len(result_df) > 1
        and isinstance(result_df.index, pd.DatetimeIndex)
    ):
        try:
            median_diff = result_df.index.to_series().diff().median().total_seconds()
            if median_diff <= 60:
                periods_per_year = 252 * 24 * 60
            elif median_diff <= 3600:
                periods_per_year = 252 * 24
            elif median_diff <= 86400:
                periods_per_year = 252
            elif median_diff <= 86400 * 7:
                periods_per_year = 52
            else:
                periods_per_year = 12
        except Exception:
            periods_per_year = 252
    cagr = (
        calc_cagr(result_df["equity"], periods_per_year)
        if "equity" in result_df.columns
        else total_return
    )

    # === 1. 頁面標題列（TradingView 風格）===
    # 動態時間範圍（從資料時間）
    if isinstance(result_df.index, pd.DatetimeIndex) and len(result_df) > 0:
        date_start = result_df.index.min().strftime("%b %-d, %Y")
        date_end = result_df.index.max().strftime("%b %-d, %Y")
    else:
        date_start = "—"
        date_end = "—"

    # 損益顏色：正綠、負紅
    pnl_color = p["green_text"] if net_profit >= 0 else p["red_text"]
    pnl_sign = "+" if net_profit >= 0 else ""

    # 標題列 HTML（含 Buy & Hold toggle、Absolute/Percent toggle）
    # 注意：用 session_state 儲存 toggle 狀態
    if "show_buy_hold" not in st.session_state:
        st.session_state["show_buy_hold"] = True
    if "show_absolute" not in st.session_state:
        st.session_state["show_absolute"] = True  # True=金額 / False=百分比

    # 標題列分兩行：左邊標題，右邊 controls
    # 用 columns 讓 toggle 用 st.checkbox（可互動）
    title_col, toggle_col = st.columns([3, 1])

    with title_col:
        st.markdown(f"""
<div>
        <h2 style="
            color: {p['text_primary']};
            font-size: 22px;
            font-weight: 600;
            margin: 0 0 4px 0;
            letter-spacing: -0.01em;
        ">Strategy Backtest Report</h2>
    <div style="
        color: {p['text_muted']};
        font-size: 12px;
        font-family: {p['font_mono']};
    ">{date_start} → {date_end} · {n_trades} trades · Initial ${initial_capital:,.0f}</div>
</div>
""", unsafe_allow_html=True)

    with toggle_col:
        # Buy & Hold toggle：用 st.toggle (segmented control 風格) — 替代原本的 HTML checkbox + streamlit checkbox 雙重顯示
        # v10 改進：清理舊版可能殘留的 session_state widget key，
        # 避免 streamlit 偵測到重複的 widget 註冊（DuplicateElementKey）。
        # 同時保持主要 key 名稱不變，確保 state 持久性。
        _widget_key = "tv_show_buy_hold_main"
        # 清理舊版本可能留下的 session_state 殘留（多餘 key 會導致 widget 衝突）
        for _old_key in list(st.session_state.keys()):
            if _old_key.startswith("tv_show_buy_hold") and _old_key != _widget_key:
                del st.session_state[_old_key]
        st.session_state["show_buy_hold"] = st.checkbox(
            "買入持有",
            value=st.session_state["show_buy_hold"],
            key=_widget_key,
        )

        # 絕對/百分比 toggle：v9 改為 segmented button 群組
        # 原本下方還有一個 st.radio，與視覺按鈕完全重複 → 已移除
        # 改用兩個 st.button 並排，type=primary/secondary 控制藍白配色
        cur_abs = st.session_state["show_absolute"]
        btn_left, btn_right = st.columns(2, gap="small")
        with btn_left:
            if st.button(
                "絕對值",
                key="tv_abs_btn",
                use_container_width=True,
                type="primary" if cur_abs else "secondary",
            ):
                st.session_state["show_absolute"] = True
                st.rerun()
        with btn_right:
            if st.button(
                "百分比",
                key="tv_pct_btn",
                use_container_width=True,
                type="primary" if not cur_abs else "secondary",
            ):
                st.session_state["show_absolute"] = False
                st.rerun()

    # 分隔線
    st.markdown(f"""
<div style="border-bottom: 1px solid {p['border']}; margin: 8px 0 16px 0;"></div>
""", unsafe_allow_html=True)

    # === 2. 5 大核心 KPI 卡片列（TradingView 風格）===
    # 與截圖完全對應：Total P&L / Max Equity Drawdown / Total Trades / Profitable Trades / Profit Factor
    k1, k2, k3, k4, k5 = st.columns(5)

    with k1:
        st.markdown(_tv_kpi_card_html(
            "Total P&amp;L",
            f"<span style='color: {pnl_color};'>{pnl_sign}${abs(net_profit):,.0f}</span>",
            sub=f"<span style='color: {pnl_color};'>{total_return:+.2f}%</span>",
            tooltip="策略的總損益（金額與百分比）。正值代表整體獲利，負值代表虧損",
        ), unsafe_allow_html=True)
    with k2:
        st.markdown(_tv_kpi_card_html(
            "Max equity drawdown",
            f"<span style='color: {p['red_text']};'>${max_dd_amount:,.2f}</span>",
            sub=f"<span style='color: {p['red_text']};'>{max_dd:.2f}%</span>",
            tooltip="歷史最大資金回撤：從最高點跌到最低點的最大跌幅。越小代表資金曲線越穩定",
        ), unsafe_allow_html=True)
    with k3:
        st.markdown(_tv_kpi_card_html(
            "Total trades",
            f"{n_trades:,}",
            sub="<span style='color: " + p["text_muted"] + ";'>全部交易</span>",
            tooltip="策略執行的總交易次數（包含做多與做空進出場）",
        ), unsafe_allow_html=True)
    with k4:
        win_color = p["green_text"] if win_rate >= 50 else p["red_text"]
        st.markdown(_tv_kpi_card_html(
            "Profitable trades",
            f"{n_wins:,}<span style='color: {p['text_muted']}; font-size: 14px;'>/{n_trades:,}</span>",
            sub=f"<span style='color: {win_color};'>{win_rate:.2f}%</span>",
            tooltip="獲利交易數 / 總交易數（次數）與勝率。勝率需搭配風報比一起看才有參考價值",
        ), unsafe_allow_html=True)
    with k5:
        pf_str = f"{profit_factor:.3f}" if np.isfinite(profit_factor) else "∞"
        pf_color = p["green_text"] if profit_factor > 1.5 else (p["text_primary"] if profit_factor > 1 else p["red_text"])
        st.markdown(_tv_kpi_card_html(
            "Profit factor",
            f"<span style='color: {pf_color};'>{pf_str}</span>",
            sub="<span style='color: " + p["text_muted"] + ";'>毛利 / 毛損</span>",
            tooltip="總獲利金額 / 總虧損金額。>1 代表獲利，>1.5 為良好，>2 為優秀",
        ), unsafe_allow_html=True)

    # === 3. 次要 6 指標列 ===
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    with k1:
        bh_color = p["green_text"] if buy_hold >= 0 else p["red_text"]
        st.markdown(_tv_kpi_card_html(
            "Buy &amp; Hold",
            f"<span style='color: {bh_color};'>{buy_hold:+.2f}%</span>",
            sub="<span style='color: " + p["text_muted"] + ";'>基準報酬</span>",
            tooltip="單純持有標的（不交易）的報酬率，用來比較策略的相對表現",
        ), unsafe_allow_html=True)
    with k2:
        alpha = total_return - buy_hold
        a_color = p["green_text"] if alpha > 0 else p["red_text"]
        st.markdown(_tv_kpi_card_html(
            "α 超額報酬",
            f"<span style='color: {a_color};'>{alpha:+.2f}%</span>",
            sub="<span style='color: " + p["text_muted"] + ";'>策略 - B&H</span>",
            tooltip="策略報酬減去 Buy &amp; Hold 報酬，正數代表策略跑贏持有",
        ), unsafe_allow_html=True)
    with k3:
        sh_color = p["green_text"] if sharpe > 1 else (p["text_primary"] if sharpe > 0 else p["red_text"])
        st.markdown(_tv_kpi_card_html(
            "Sharpe",
            f"<span style='color: {sh_color};'>{sharpe:.2f}</span>",
            sub="<span style='color: " + p["text_muted"] + ";'>風險調整報酬</span>",
            tooltip="（平均報酬 - 無風險利率）/ 報酬標準差。>1 為良好，>2 為優秀",
        ), unsafe_allow_html=True)
    with k4:
        so_color = p["green_text"] if sortino > 1 else (p["text_primary"] if sortino > 0 else p["red_text"])
        st.markdown(_tv_kpi_card_html(
            "Sortino",
            f"<span style='color: {so_color};'>{sortino:.2f}</span>",
            sub="<span style='color: " + p["text_muted"] + ";'>下行風險調整</span>",
            tooltip="類似 Sharpe 但只考慮下行波動，更貼近投資人對虧損的厭惡",
        ), unsafe_allow_html=True)
    with k5:
        ca_color = p["green_text"] if cagr >= 0 else p["red_text"]
        st.markdown(_tv_kpi_card_html(
            "CAGR",
            f"<span style='color: {ca_color};'>{cagr:+.2f}%</span>",
            sub="<span style='color: " + p["text_muted"] + ";'>年化報酬</span>",
            tooltip="年複合成長率：把回測期間的總報酬換算為年化報酬",
        ), unsafe_allow_html=True)
    with k6:
        cm_color = p["green_text"] if calmar > 1 else (p["text_primary"] if calmar > 0 else p["red_text"])
        st.markdown(_tv_kpi_card_html(
            "Calmar",
            f"<span style='color: {cm_color};'>{calmar:.2f}</span>",
            sub="<span style='color: " + p["text_muted"] + ";'>CAGR / MaxDD</span>",
            tooltip="CAGR 除以最大回撤的絕對值，衡量每承擔一單位回撤能獲得多少年化報酬",
        ), unsafe_allow_html=True)

    # === 4. 主圖：權益曲線 + Buy & Hold + Drawdown（TradingView 風格）===
    st.markdown(f"""
<div style="
    color: {p['text_secondary']};
    font-size: 11px;
    text-transform: none;
    letter-spacing: 0;
    font-weight: 600;
    margin: 24px 0 8px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid {p['border']};
">Equity Curve &amp; Drawdown</div>
""", unsafe_allow_html=True)

    _render_tv_equity_chart(result_df, metrics_with_cap, st.session_state["show_buy_hold"])

    # === 5. 交易統計 KPI 網格（4×3 = 12 個）===
    st.markdown(f"""
<div style="
    color: {p['text_secondary']};
    font-size: 11px;
    text-transform: none;
    letter-spacing: 0;
    font-weight: 600;
    margin: 28px 0 8px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid {p['border']};
">Trade Statistics</div>
""", unsafe_allow_html=True)

    _render_trade_stats_grid(metrics, n_trades, n_wins, win_rate, profit_factor, avg_win, avg_loss, rr, recovery, p)


def _render_tv_equity_chart(result_df: pd.DataFrame, metrics: Dict, show_buy_hold: bool = True) -> None:
    """TradingView 風格主圖（權益 + Drawdown）— v6 改進：

    - 漸層陰影取代整片死板填色
    - 買賣點 y 對齊 equity 曲線（不是 close 價）— 精準貼在線上
    - TradingView 配色：綠 #26A69A、紅 #EF5350
    - 主圖 + Drawdown 共用 X 軸（hover 統一）
    - 線條抗鋸齒（spline 平滑）
    """
    p = _palette()
    initial_capital = metrics.get("initial_capital", 10000)
    net_profit = metrics.get("final_equity", initial_capital) - initial_capital
    is_profit = net_profit >= 0

    # === TradingView 配色 ===
    tv_green = "#0D9488"   # Tiffany 綠
    tv_red = "#EF5350"
    tv_orange = "#FF9800"  # 亮橘

    equity_color = tv_green if is_profit else tv_red

    # 漸層：頂部最濃 → 底部透明
    if is_profit:
        gradient_layers = [
            ("rgba(13, 148, 136, 0.04)", 0.25),
            ("rgba(13, 148, 136, 0.10)", 0.50),
            ("rgba(13, 148, 136, 0.18)", 0.75),
            ("rgba(13, 148, 136, 0.28)", 1.00),
        ]
    else:
        gradient_layers = [
            ("rgba(239, 83, 80, 0.04)", 0.25),
            ("rgba(239, 83, 80, 0.10)", 0.50),
            ("rgba(239, 83, 80, 0.18)", 0.75),
            ("rgba(239, 83, 80, 0.28)", 1.00),
        ]

    equity = result_df["equity"]
    cummax = equity.cummax()
    drawdown_pct = (equity - cummax) / cummax * 100

    # === 主圖 + Drawdown 子圖（65% / 35%，X 軸共享）===
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.65, 0.35],
    )

    # === 1. 漸層陰影（4 層堆疊，模擬 TV 的細緻漸層）===
    # 從最小 alpha 開始疊（最後加的最深）
    for fill_rgba, scale in gradient_layers:
        # 計算 y 值：equity * scale（從底部向上）
        # 這會產生從 0 到 equity 的漸層效果
        y_grad = equity * scale
        fig.add_trace(go.Scatter(
            x=result_df.index,
            y=y_grad,
            mode="lines",
            line=dict(width=0, color="rgba(0,0,0,0)"),  # 隱形線
            fill="tozeroy",
            fillcolor=fill_rgba,
            showlegend=False,
            hoverinfo="skip",
        ), row=1, col=1)

    # === 2. 主策略權益曲線（粗線 + spline 抗鋸齒）===
    fig.add_trace(go.Scatter(
        x=result_df.index,
        y=equity,
        name="策略權益",
        mode="lines",
        line=dict(color=equity_color, width=2.4, shape="spline", smoothing=0.6),
        hovertemplate="<b>%{x|%Y-%m-%d %H:%M}</b><br>策略權益: $%{y:,.2f}<extra></extra>",
    ), row=1, col=1)

    # === 3. Buy & Hold 基準線（虛線，TV 風格）===
    if show_buy_hold and "buy_hold" in result_df.columns:
        fig.add_trace(go.Scatter(
            x=result_df.index,
            y=result_df["buy_hold"],
            name="Buy &amp; Hold",
            mode="lines",
            line=dict(color=tv_orange, width=1.3, dash="dash", shape="spline", smoothing=0.6),
            opacity=0.85,
            hovertemplate="<b>%{x|%Y-%m-%d %H:%M}</b><br>Buy & Hold: $%{y:,.2f}<extra></extra>",
        ), row=1, col=1)

    # === 4. 進場做多 marker（綠色向上三角，y 對齊 equity）===
    if "entry" in result_df.columns and "position" in result_df.columns:
        long_mask = result_df["entry"] & (result_df["position"] == 1)
        long_entries = result_df[long_mask]
        if not long_entries.empty:
            # y 用 equity（不是 close 價）— 確保 marker 精準貼在 equity 線上
            fig.add_trace(go.Scatter(
                x=long_entries.index,
                y=long_entries["equity"],  # ← 關鍵修正：用 equity 對齊曲線
                mode="markers",
                name="做多進場",
                marker=dict(
                    symbol="triangle-up",
                    size=10,
                    color=tv_green,
                    line=dict(color="white", width=1.2),
                ),
                hovertemplate="<b>%{x|%Y-%m-%d}</b><br>做多進場<br>權益：$%{y:,.2f}<extra></extra>",
            ), row=1, col=1)

        # 5. 進場做空 marker（紅色向下三角）
        short_mask = result_df["entry"] & (result_df["position"] == -1)
        short_entries = result_df[short_mask]
        if not short_entries.empty:
            fig.add_trace(go.Scatter(
                x=short_entries.index,
                y=short_entries["equity"],  # ← 對齊 equity
                mode="markers",
                name="做空進場",
                marker=dict(
                    symbol="triangle-down",
                    size=10,
                    color=tv_red,
                    line=dict(color="white", width=1.2),
                ),
                hovertemplate="<b>%{x|%Y-%m-%d}</b><br>做空進場<br>權益：$%{y:,.2f}<extra></extra>",
            ), row=1, col=1)

    # === 6. 出場 marker（橘色叉，y 對齊 equity）===
    if "exit" in result_df.columns:
        exits = result_df[result_df["exit"]]
        if not exits.empty:
            fig.add_trace(go.Scatter(
                x=exits.index,
                y=exits["equity"],  # ← 對齊 equity
                mode="markers",
                name="出場",
                marker=dict(
                    symbol="x-thin",
                    size=9,
                    color=tv_orange,
                    line=dict(color=tv_orange, width=2.2),
                ),
                hovertemplate="<b>%{x|%Y-%m-%d}</b><br>出場<br>權益：$%{y:,.2f}<extra></extra>",
            ), row=1, col=1)

    # === 7. Drawdown 子圖（TV 風格：紅色面積 + 線）===
    fig.add_trace(go.Scatter(
        x=result_df.index,
        y=drawdown_pct,
        name="回撤",
        mode="lines",
        line=dict(color=tv_red, width=1.1, shape="spline", smoothing=0.4),
        fill="tozeroy",
        fillcolor="rgba(239, 83, 80, 0.18)",  # TV 紅色 18% alpha
        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>回撤：%{y:.2f}%<extra></extra>",
    ), row=2, col=1)

    # === Layout（TV 風格）===
    hover_bg = "rgba(28, 31, 42, 0.9)"
    hover_border = "rgba(80, 85, 100, 0.3)"
    fig.update_layout(
        height=560,
        hovermode="x unified",
        template=get_current_theme()["plotly_template"],
        paper_bgcolor=p["bg"],
        plot_bgcolor=p["bg"],
        font=dict(color=p["text_primary"], family="system-ui", size=12),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.0,
            xanchor="left", x=0,
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(0,0,0,0)",
            borderwidth=0,
            font=dict(size=11, color=p["text_secondary"]),
        ),
        hoverlabel=dict(
            bgcolor=hover_bg,
            bordercolor=hover_border,
            font=dict(color="#FFFFFF", size=12),
            align="left",
            namelength=-1,
        ),
        margin=dict(l=70, r=16, t=8, b=36),
        xaxis=dict(
            gridcolor=p["border"],
            showgrid=True,
            zeroline=False,
            rangeslider=dict(visible=False),
            showline=False,
            gridwidth=1,
            griddash="dot",
            tickfont=dict(size=10, color=p["text_muted"], family=p["font_mono"]),
        ),
        xaxis2=dict(
            gridcolor=p["border"],
            showgrid=False,
            zeroline=False,
            griddash="dot",
            tickfont=dict(size=10, color=p["text_muted"], family=p["font_mono"]),
        ),
        yaxis=dict(
            gridcolor=p["border"],
            showgrid=True,
            zeroline=False,
            side="left",
            title=None,
            gridwidth=1,
            griddash="dot",
            tickfont=dict(size=10, color=p["text_muted"], family=p["font_mono"]),
            ticks="outside",
            ticklen=4,
            tickcolor=p["border"],
            nticks=6,
            tickformat=",.0s",
            rangemode="normal",
        ),
        yaxis2=dict(
            gridcolor=p["border"],
            showgrid=True,
            zeroline=False,
            side="left",
            title=None,
            gridwidth=1,
            griddash="dot",
            tickfont=dict(size=10, color=p["text_muted"], family=p["font_mono"]),
            ticks="outside",
            ticklen=4,
            tickcolor=p["border"],
            nticks=4,
            tickformat=".0f",
            rangemode="tozero",
        ),
    )

    # X 軸時間格式（自動）
    try:
        if isinstance(result_df.index, pd.DatetimeIndex):
            median_diff = result_df.index.to_series().diff().median().total_seconds()
            if median_diff <= 86400 * 3:
                fig.update_xaxes(tickformat="%Y-%m-%d")
            else:
                fig.update_xaxes(tickformat="%Y-%m")
    except Exception:
        pass

    st.plotly_chart(fig, use_container_width=True, config={"staticPlot": True, "displayModeBar": False})


def _render_trade_stats_grid(
    metrics: Dict,
    n_trades: int,
    n_wins: int,
    win_rate: float,
    profit_factor: float,
    avg_win: float,
    avg_loss: float,
    rr: float,
    recovery: float,
    p: Dict[str, str],
) -> None:
    """交易統計 KPI 4×3 網格。"""
    n_losses = n_trades - n_wins
    net_profit = metrics.get("final_equity", 10000) - metrics.get("initial_capital", 10000)
    max_dd = metrics.get("max_drawdown_pct", 0)
    total_return = metrics.get("total_return_pct", 0)
    largest_win = metrics.get("largest_win_pct", 0)
    largest_loss = metrics.get("largest_loss_pct", 0)
    buy_hold = metrics.get("buy_hold_return_pct", 0)
    sharpe = metrics.get("sharpe_ratio", 0)
    max_consec_w = metrics.get("max_consecutive_wins", 0)
    max_consec_l = metrics.get("max_consecutive_losses", 0)
    avg_trade_duration = metrics.get("avg_trade_duration_hours", 0)

    rows_data = [
        # 第 1 列：交易概覽
        [
            ("Total trades", f"{n_trades:,}", "中性"),
            ("Profitable trades", f"{n_wins:,}", "正" if n_wins > 0 else "中性"),
            ("Losing trades", f"{n_losses:,}", "負" if n_losses > 0 else "中性"),
            ("Win rate", f"{win_rate:.2f}%", "正" if win_rate >= 50 else "負"),
        ],
        # 第 2 列：利潤統計
        [
            ("Net profit", f"${net_profit:+,.2f}", "正" if net_profit > 0 else "負"),
            ("Total return", f"{total_return:+.2f}%", "正" if total_return >= 0 else "負"),
            ("Avg win", f"{avg_win:+.2f}%", "正"),
            ("Avg loss", f"{avg_loss:+.2f}%", "負"),
        ],
        # 第 3 列：風險指標
        [
            ("Profit factor", f"{profit_factor:.2f}" if np.isfinite(profit_factor) else "∞",
             "正" if profit_factor > 1.5 else "中性"),
            ("Risk/Reward", f"{rr:.2f}" if rr > 0 else "∞", "正" if rr > 1 else "負"),
            ("Max drawdown", f"{abs(max_dd):.2f}%", "負" if abs(max_dd) > 20 else "中性"),
            ("Recovery factor", f"{recovery:.2f}", "正" if recovery > 1 else "中性"),
        ],
        # 第 4 列：極值 + 連續
        [
            ("Largest win", f"{largest_win:+.2f}%", "正"),
            ("Largest loss", f"{largest_loss:+.2f}%", "負"),
            ("Max consec. wins", f"{max_consec_w}", "正"),
            ("Max consec. losses", f"{max_consec_l}", "負"),
        ],
    ]

    for r_idx, row_data in enumerate(rows_data):
        cols = st.columns(4)
        for c_idx, (label, value, sentiment) in enumerate(row_data):
            if sentiment == "正":
                color = p["green_text"]
            elif sentiment == "負":
                color = p["red_text"]
            else:
                color = p["text_primary"]
            with cols[c_idx]:
                st.markdown(_tv_kpi_card_html(
                    label,
                    f"<span style='color: {color};'>{value}</span>",
                ), unsafe_allow_html=True)
        if r_idx < len(rows_data) - 1:
            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)


# === Overview 頁：KPI 卡片 + 主圖 + 交易統計 ===
def render_overview(
    metrics: Dict,
    result_df: pd.DataFrame,
    initial_capital: float,
    trades: Optional[List[Dict]] = None,
) -> None:
    """TradingView Strategy Tester 風格 Overview。

    trades 為可選參數：傳入時可確保 n_wins / win_rate 計算一致
    （不會再有「1/6 但 33.33%」這種顯示矛盾）。
    """
    # v4+ 改為 TradingView 風格（重設計）
    render_tv_overview(metrics, result_df, initial_capital, trades=trades)


def render_performance_summary(trades: List[Dict], metrics: Dict) -> None:
    """Performance Summary 頁：交易統計網格 + 月報酬熱圖。"""
    p = _palette()

    if not trades:
        st.info("無交易記錄")
        return

    trades_df = pd.DataFrame(trades)

    # 多維度分組
    blocks = [
        ("全部交易", trades_df),
        ("做多", trades_df[trades_df["direction"] == "long"] if "direction" in trades_df.columns else pd.DataFrame()),
        ("做空", trades_df[trades_df["direction"] == "short"] if "direction" in trades_df.columns else pd.DataFrame()),
    ]

    for title, df_block in blocks:
        if df_block.empty:
            continue

        st.markdown(f"""
<div style="
    font-size: 0.95rem;
    font-weight: 600;
    color: {p['text_primary']};
    margin: 24px 0 12px 0;
    padding-bottom: 8px;
    border-bottom: 1px solid {p['border']};
">{title}</div>
""", unsafe_allow_html=True)

        n = len(df_block)
        winners = df_block[df_block["pnl"] > 0]
        losers = df_block[df_block["pnl"] <= 0]
        win_rate = len(winners) / n * 100 if n > 0 else 0
        net_profit = df_block["pnl"].sum()
        gross_profit = winners["pnl"].sum() if len(winners) > 0 else 0
        gross_loss = abs(losers["pnl"].sum()) if len(losers) > 0 else 0
        avg_win = winners["pnl_pct"].mean() * 100 if len(winners) > 0 else 0
        avg_loss = losers["pnl_pct"].mean() * 100 if len(losers) > 0 else 0
        largest_win = df_block["pnl_pct"].max() * 100
        largest_loss = df_block["pnl_pct"].min() * 100
        avg_duration = df_block["duration_hours"].mean() if "duration_hours" in df_block.columns else 0
        max_consec_wins = _max_consecutive(df_block["pnl"] > 0)
        max_consec_losses = _max_consecutive(df_block["pnl"] <= 0)
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        rr = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

        # TradingView 風格：4x4 KPI 網格
        rows = [
            [
                _kpi_card_html("交易數", f"{n}"),
                _kpi_card_html("獲利", f"{len(winners)}", "positive" if len(winners) > 0 else "neutral"),
                _kpi_card_html("虧損", f"{len(losers)}", "negative" if len(losers) > 0 else "neutral"),
                _kpi_card_html("勝率", f"{win_rate:.1f}%", "positive" if win_rate >= 50 else "negative"),
            ],
            [
                _kpi_card_html("淨利潤", f"${net_profit:+,.2f}", "positive" if net_profit > 0 else "negative"),
                _kpi_card_html("毛利", f"${gross_profit:,.2f}", "positive"),
                _kpi_card_html("毛損", f"${gross_loss:,.2f}", "negative"),
                _kpi_card_html("Profit Factor", f"{pf:.2f}" if np.isfinite(pf) else "∞",
                                 "positive" if pf > 1.5 else ("neutral" if pf > 1 else "negative")),
            ],
            [
                _kpi_card_html("平均獲利", f"{avg_win:+.2f}%", "positive"),
                _kpi_card_html("平均虧損", f"{avg_loss:+.2f}%", "negative"),
                _kpi_card_html("最大單筆獲利", f"{largest_win:+.2f}%", "positive"),
                _kpi_card_html("最大單筆虧損", f"{largest_loss:+.2f}%", "negative"),
            ],
            [
                _kpi_card_html("風報比", f"{rr:.2f}" if np.isfinite(rr) else "∞",
                                 "positive" if rr > 1 else "negative"),
                _kpi_card_html("平均持倉 (h)", f"{avg_duration:.1f}"),
                _kpi_card_html("最大連勝", f"{max_consec_wins}", "positive"),
                _kpi_card_html("最大連敗", f"{max_consec_losses}", "negative"),
            ],
        ]

        # 渲染 4x4 網格
        for r_idx, row in enumerate(rows):
            cols = st.columns(4)
            for c_idx, card_html in enumerate(row):
                with cols[c_idx]:
                    st.markdown(card_html, unsafe_allow_html=True)
            if r_idx < len(rows) - 1:
                st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # === 月報酬熱圖（Impeccable 風格）===
    st.markdown(f"""
<div style="
    color: {p['text_secondary']};
    font-size: 11px;
    text-transform: none;
    letter-spacing: 0;
    font-weight: 600;
    margin: 32px 0 8px 0;
    padding-bottom: 8px;
    border-bottom: 1px solid {p['border']};
">月報酬熱圖</div>
""", unsafe_allow_html=True)

    # 雙重保險：即使 monthly_heatmap 內部出錯也不會讓整頁崩潰
    try:
        render_monthly_heatmap(trades_df, p)
    except Exception as _heatmap_err:
        st.caption(f"月報酬熱圖暫時無法顯示（{type(_heatmap_err).__name__}）")


def render_monthly_heatmap(trades_df: pd.DataFrame, p: dict) -> None:
    """月報酬熱圖（TradingView 風格）。

    X 軸：年（2014、2015、…）
    Y 軸：月（Jan-Dec）
    Cell：該月報酬 %（綠正 / 紅負）
    """
    # 入口守衛：先確認 trades_df 有效，避免任何欄位缺失導致整頁崩潰
    if trades_df is None or not isinstance(trades_df, pd.DataFrame) or trades_df.empty:
        st.caption("無交易記錄或缺少 exit_time 欄位")
        return
    if "exit_time" not in trades_df.columns:
        st.caption("無交易記錄或缺少 exit_time 欄位")
        return
    if "pnl" not in trades_df.columns:
        st.caption("無交易記錄或缺少 pnl 欄位")
        return

    # 確保 exit_time 是 datetime
    if not pd.api.types.is_datetime64_any_dtype(trades_df["exit_time"]):
        trades_df = trades_df.copy()
        trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"], errors="coerce")
    trades_df = trades_df.dropna(subset=["exit_time"])

    if trades_df.empty:
        st.caption("無有效交易時間")
        return

    # 計算每月報酬
    try:
        trades_df["year"] = trades_df["exit_time"].dt.year
        trades_df["month"] = trades_df["exit_time"].dt.month
        monthly_pnl = trades_df.groupby(["year", "month"])["pnl"].sum().reset_index()
    except Exception as e:
        st.caption(f"月報酬熱圖計算失敗：{type(e).__name__}")
        return

    # 計算每月報酬率（用累積 PnL / 初始資金估算，簡化版）
    # 這裡用「相對於當時權益」做近似：當月 PnL / 初始資金 * 100
    # 更精確版本可從 result_df 取得 equity，但這裡用近似
    initial_capital = 10000  # 預設值；實際從 metrics 拿
    monthly_pnl["return_pct"] = (monthly_pnl["pnl"] / initial_capital) * 100

    # 建立熱圖 matrix
    years = sorted(monthly_pnl["year"].unique())
    months = list(range(1, 13))
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    z = np.full((len(months), len(years)), np.nan)
    for _, row in monthly_pnl.iterrows():
        y_idx = years.index(row["year"])
        m_idx = months.index(row["month"])
        z[m_idx, y_idx] = row["return_pct"]

    # 自訂 hover 文字
    text = [[f"{month_labels[m]} {years[y]}<br>{z[m, y]:+.2f}%" if not np.isnan(z[m, y]) else ""
              for y in range(len(years))]
             for m in range(len(months))]

    # Colorscale：綠 → 白 → 紅（Impeccable 風格，不用紫色）
    max_abs = np.nanmax(np.abs(z)) if not np.isnan(z).all() else 1
    if max_abs == 0:
        max_abs = 1

    colorscale = [
        [0.0, p["red"]],       # 負
        [0.5, p["bg_card"]],   # 0（白色 / 卡片色）
        [1.0, p["green"]],     # 正
    ]

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=[str(y) for y in years],
        y=month_labels,
        text=text,
        texttemplate="%{text}",
        textfont=dict(size=10, color=p["text_primary"], family=p["font_mono"]),
        colorscale=colorscale,
        zmid=0,
        zmin=-max_abs,
        zmax=max_abs,
        xgap=2, ygap=2,
        colorbar=dict(
            title=dict(text="月報酬 %", font=dict(size=11, color=p["text_secondary"])),
            tickfont=dict(size=10, color=p["text_secondary"]),
            thickness=12,
            len=0.6,
        ),
        hovertemplate="%{text}<extra></extra>",
    ))

    fig.update_layout(
        height=380,
        template=p.get("plotly_template", "plotly_white"),
        paper_bgcolor=p["bg"],
        plot_bgcolor=p["bg"],
        font=dict(color=p["text_primary"], family="system-ui", size=12),
        margin=dict(l=60, r=60, t=16, b=40),
        xaxis=dict(
            side="top",
            tickfont=dict(size=11, color=p["text_secondary"]),
            showgrid=False,
        ),
        yaxis=dict(
            autorange="reversed",
            tickfont=dict(size=11, color=p["text_secondary"]),
            showgrid=False,
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config={"staticPlot": True, "displayModeBar": False})

    # 熱圖下方：年度總報酬摘要
    # v8 改進：完整防呆 — year 欄位不存在、pnl 為空、return_pct 缺失都安全處理
    yearly_summary = pd.DataFrame(columns=["年度", "總損益 (USDT)", "年度報酬 %"])
    try:
        if "year" in trades_df.columns and "pnl" in trades_df.columns and not trades_df.empty:
            _ys = trades_df.groupby("year")["pnl"].sum().reset_index()
            if not _ys.empty and len(_ys) > 0:
                # 確保 initial_capital 不是 0（避免除以 0）
                _cap = initial_capital if initial_capital else 1
                _ys["return_pct"] = (_ys["pnl"] / _cap) * 100
                _ys.columns = ["年度", "總損益 (USDT)", "年度報酬 %"]
                yearly_summary = _ys
    except Exception as e:
        # 任何計算錯誤 → 保持空 DataFrame
        yearly_summary = pd.DataFrame(columns=["年度", "總損益 (USDT)", "年度報酬 %"])

    st.markdown(f"""
<div style="
    color: {p['text_secondary']};
    font-size: 11px;
    text-transform: none;
    letter-spacing: 0;
    font-weight: 600;
    margin: 16px 0 8px 0;
">年度總覽</div>
""", unsafe_allow_html=True)

    # 3 欄：今年度、上年度、平均
    # v8 防呆：yearly_summary 空 / 欄位缺失 → 全部用 0 預設值
    if len(yearly_summary) > 0 and "年度報酬 %" in yearly_summary.columns:
        c1, c2, c3 = st.columns(3)
        with c1:
            # 防呆：取得「今年度」用 .iloc[-1]，若無資料則用 0
            try:
                latest = yearly_summary.iloc[-1]
                latest_year = int(latest.get("年度", 0)) if "年度" in yearly_summary.columns else 0
                latest_pnl = float(latest.get("總損益 (USDT)", 0)) if "總損益 (USDT)" in yearly_summary.columns else 0
                latest_pct = float(latest.get("年度報酬 %", 0)) if "年度報酬 %" in yearly_summary.columns else 0
            except (IndexError, KeyError, ValueError):
                latest_year, latest_pnl, latest_pct = 0, 0, 0
            st.markdown(_kpi_card_html(
                f"{latest_year} 年度" if latest_year else "今年度",
                f"${latest_pnl:+,.0f}" if latest_pnl else "$0",
                "positive" if latest_pnl > 0 else ("negative" if latest_pnl < 0 else "neutral"),
                sub=f"{latest_pct:+.2f}%" if latest_pct else "—",
            ), unsafe_allow_html=True)
        with c2:
            # 防呆：計算平均值，若欄位缺失或全空 → 0
            try:
                if "年度報酬 %" in yearly_summary.columns and not yearly_summary["年度報酬 %"].isna().all():
                    avg = float(yearly_summary["年度報酬 %"].mean())
                else:
                    avg = 0
                n_years = int(len(yearly_summary))
            except (KeyError, ValueError, TypeError):
                avg, n_years = 0, 0
            st.markdown(_kpi_card_html(
                "歷年平均",
                f"{avg:+.2f}%",
                "positive" if avg > 0 else ("negative" if avg < 0 else "neutral"),
                sub=f"{n_years} 年" if n_years else "—",
            ), unsafe_allow_html=True)
        with c3:
            # 防呆：取得「最佳年度」用 idxmax，若全空或缺失 → 0
            try:
                if "年度報酬 %" in yearly_summary.columns and not yearly_summary["年度報酬 %"].isna().all():
                    best = yearly_summary.loc[yearly_summary["年度報酬 %"].idxmax()]
                    best_year = int(best.get("年度", 0))
                    best_pnl = float(best.get("總損益 (USDT)", 0))
                    best_pct = float(best.get("年度報酬 %", 0))
                else:
                    best_year, best_pnl, best_pct = 0, 0, 0
            except (KeyError, ValueError, TypeError):
                best_year, best_pnl, best_pct = 0, 0, 0
            st.markdown(_kpi_card_html(
                f"最佳年度 ({best_year})" if best_year else "最佳年度",
                f"${best_pnl:+,.0f}" if best_pnl else "$0",
                "positive" if best_pnl > 0 else "neutral",
                sub=f"{best_pct:+.2f}%" if best_pct else "—",
            ), unsafe_allow_html=True)
    else:
        # 邊界：yearly_summary 完全沒資料 → 顯示提示
        st.caption("無足夠資料計算年度總覽（缺少年份或 PnL 資訊）")


def render_list_of_trades(trades: List[Dict]) -> None:
    """List of Trades 頁：交易明細表（v2: streamlit-aggrid + 點擊高亮圖表）。"""
    p = _palette()

    if not trades:
        st.info("無交易記錄")
        return

    trades_df = pd.DataFrame(trades)

    if "entry_time" in trades_df.columns:
        trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"]).dt.tz_localize(None)
    if "exit_time" in trades_df.columns:
        trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"]).dt.tz_localize(None)

    trades_df["累計 PnL"] = trades_df["pnl"].cumsum().round(2)

    if "duration_hours" in trades_df.columns:
        trades_df["duration_hours"] = trades_df["duration_hours"].round(2)
    if "pnl_pct" in trades_df.columns:
        trades_df["pnl_pct"] = (trades_df["pnl_pct"] * 100).round(2)
    if "pnl" in trades_df.columns:
        trades_df["pnl"] = trades_df["pnl"].round(2)
    if "entry_price" in trades_df.columns:
        trades_df["entry_price"] = trades_df["entry_price"].round(2)
    if "exit_price" in trades_df.columns:
        trades_df["exit_price"] = trades_df["exit_price"].round(2)

    rename_map = {
        "entry_time": "進場時間",
        "exit_time": "出場時間",
        "direction": "方向",
        "entry_price": "進場價",
        "exit_price": "出場價",
        "pnl_pct": "報酬 %",
        "pnl": "損益 (USDT)",
        "duration_hours": "持倉 (h)",
        "exit_reason": "出場原因",
    }
    trades_df_display = trades_df.rename(columns=rename_map)

    st.markdown(f"""
<div style="
    color: {p['text_secondary']};
    font-size: 11px;
    text-transform: none;
    letter-spacing: 0;
    font-weight: 600;
    margin-bottom: 8px;
    margin-top: 4px;
">交易明細 ({len(trades_df_display)} 筆)</div>
""", unsafe_allow_html=True)

    # v2: 用 streamlit-aggrid 支援 row click → 圖表高亮
    st.caption("提示：點擊任一交易，圖表會自動顯示該交易的進出場位置與損益")

    # 雙重保險：若 streamlit-aggrid 未安裝，用 st.dataframe 替代而不崩潰
    try:
        from st_aggrid import AgGrid, GridOptionsBuilder, JsCode, GridUpdateMode
        _HAS_AGGRID = True
    except ImportError:
        _HAS_AGGRID = False
        st.warning(" streamlit-aggrid 未安裝，使用簡易表格替代（功能受限）")
        st.dataframe(trades_df_display.drop(columns=["累計 PnL"], errors="ignore"),
                      use_container_width=True, hide_index=True)
        st.download_button(
            "下載交易明細 CSV",
            data=trades_df_display.drop(columns=["#"]).to_csv(index=False).encode("utf-8"),
            file_name=f"trades_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key="trades_csv_simple",
        )
        return

    import streamlit as st_lib  # 用別名避免 shadowing

    # 給每個 trade 唯一 ID（用 index）
    trades_df_display = trades_df_display.copy()
    trades_df_display.insert(0, "#", trades_df_display.index)

    # 顏色 cell renderer：盈虧綠紅
    # aggrid 32.2+ cellStyle 接受 function(params) 或 object
    # 注意：cell 文字可能是 -9.48（純數字）或 -9.48%
    # 用字串 function（aggrid 32+ 直接執行字串 JS）
    pnl_color_js = JsCode(f"""
    function(params) {{
        if (params.value == null) return null;
        const val = params.value;
        const isNeg = (typeof val === 'number' && val < 0) ||
                       (typeof val === 'string' && (val.trim().startsWith('-') || val.includes('-')));
        if (isNeg) {{
            return {{ 'color': '{p["red_text"]}', 'fontWeight': '600' }};
        }}
        const isPos = (typeof val === 'number' && val > 0) ||
                       (typeof val === 'string' && val.trim().startsWith('+'));
        if (isPos) {{
            return {{ 'color': '{p["green_text"]}', 'fontWeight': '600' }};
        }}
        return null;
    }}
    """)

    direction_color_js = JsCode(f"""
    function(params) {{
        if (params.value === 'long') {{
            return {{ 'color': '{p["green_text"]}', 'fontWeight': '600' }};
        }} else if (params.value === 'short') {{
            return {{ 'color': '{p["red_text"]}', 'fontWeight': '600' }};
        }}
        return null;
    }}
    """)

    gb = GridOptionsBuilder.from_dataframe(trades_df_display)
    # v32.2+ 用 object-style rowSelection
    pre_sel_idx = st_lib.session_state.get("selected_trade_row")
    pre_selected = [str(pre_sel_idx)] if pre_sel_idx is not None else []
    gb.configure_selection(
        selection_mode="single",
        use_checkbox=False,
        pre_selected_rows=pre_selected,
    )
    gb.configure_grid_options(domLayout="normal")
    # cellStyle JS 在 aggrid 32.2+ 用 JsCode 套色（streamlit-aggrid 1.2.1 會處理）
    try:
        gb.configure_column("報酬 %", cellStyle=pnl_color_js)
    except Exception:
        pass
    try:
        gb.configure_column("損益 (USDT)", cellStyle=pnl_color_js)
    except Exception:
        pass
    try:
        gb.configure_column("累計 PnL", cellStyle=pnl_color_js)
    except Exception:
        pass
    try:
        gb.configure_column("方向", cellStyle=direction_color_js)
    except Exception:
        pass
    # 不要顯示「#」欄（純內部 ID）
    gb.configure_column("#", hide=True)
    grid_options = gb.build()

    # 主題：依當前主題
    aggrid_theme = "alpine" if p["bg"] == p.get("bg") and p.get("text_primary") == "#0F172A" else "alpine-dark"
    # 簡化判斷：淺色用 alpine，深色用 alpine-dark
    is_dark = p.get("text_primary", "").startswith("#F") or p.get("text_primary", "").startswith("#f")
    aggrid_theme = "alpine-dark" if is_dark else "alpine"

    # 計算高度：每列 28px，header 32px，最少 300px
    grid_height = min(500, max(300, 32 + 28 * len(trades_df_display)))

    grid_response = AgGrid(
        trades_df_display,
        grid_options,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        fit_columns_on_grid_load=True,
        theme=aggrid_theme,
        height=grid_height,
        key="trades_aggrid",
        allow_unsafe_jscode=True,
    )

    # 處理選擇：將選中的 row 存到 session_state
    selected_rows = grid_response.get("selected_rows", [])
    if selected_rows is None:
        selected_rows = []
    # 兼容 DataFrame 與 list
    if hasattr(selected_rows, "to_dict"):
        selected_rows = selected_rows.to_dict("records")

    new_selected = None
    if len(selected_rows) > 0:
        row = selected_rows[0] if isinstance(selected_rows, list) else selected_rows.iloc[0]
        if isinstance(row, dict):
            new_selected = int(row.get("#", -1))
        else:
            new_selected = int(row["#"])

    if new_selected is not None and 0 <= new_selected < len(trades):
        prev = st_lib.session_state.get("selected_trade_row")
        if prev != new_selected:
            st_lib.session_state["selected_trade_row"] = new_selected
            # 不 rerun — 避免切到其他 tab 時回到 Overview
    else:
        # 清空選擇
        if st_lib.session_state.get("selected_trade_row") is not None:
            st_lib.session_state["selected_trade_row"] = None

    # 顯示選中交易的高亮資訊卡
    sel_idx = st_lib.session_state.get("selected_trade_row")
    if sel_idx is not None and 0 <= sel_idx < len(trades):
        trade = trades[sel_idx]
        render_trade_highlight_card(trade, p)
    else:
        st.markdown(f"""
<div class="empty-state" style="
    margin-top: 12px;
">
     點擊上表任一列，下方會顯示該交易詳情與圖表高亮
</div>
""", unsafe_allow_html=True)

    # 下載按鈕
    from datetime import datetime
    csv = trades_df_display.drop(columns=["#"]).to_csv(index=False).encode("utf-8")
    st.download_button(
        "下載交易明細 CSV",
        data=csv,
        file_name=f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )


def render_trade_highlight_card(trade: Dict, p: dict) -> None:
    """v2: 顯示選中交易的詳細資訊卡。"""
    entry = trade.get("entry_time", "")
    exit_ = trade.get("exit_time", "")
    direction = trade.get("direction", "?")
    pnl = trade.get("pnl", 0)
    pnl_pct = trade.get("pnl_pct", 0) * 100
    entry_price = trade.get("entry_price", 0)
    exit_price = trade.get("exit_price", 0)
    duration_h = trade.get("duration_hours", 0)
    exit_reason = trade.get("exit_reason", "?")

    is_profit = pnl >= 0
    accent = p["green_text"] if is_profit else p["red_text"]
    dir_color = p["green_text"] if direction == "long" else p["red_text"]
    dir_label = "做多" if direction == "long" else "做空"

    # 計算持倉天數
    if duration_h >= 24:
        dur_str = f"{duration_h / 24:.1f} 天"
    else:
        dur_str = f"{duration_h:.1f} 小時"

    st.markdown(f"""
<div style="
    margin-top: 12px;
    padding: 14px 18px;
    background: {p['bg_subtle']};
    border: 1px solid {p['border']};
    border-left: 1px solid {p['border']};
    border-radius: 6px;
">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
        <div style="font-size: 13px; font-weight: 600; color: {p['text_primary']};">
            交易詳情
        </div>
        <div style="
            display: inline-block;
            padding: 2px 10px;
            border-radius: 999px;
            background: {p['bg_card']};
            color: {dir_color};
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.04em;
        ">{dir_label}</div>
    </div>
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;">
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: none; letter-spacing: 0; margin-bottom: 2px;">進場時間</div>
            <div style="color: {p['text_primary']}; font-size: 12px; font-family: {p['font_mono']};">{entry}</div>
        </div>
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: none; letter-spacing: 0; margin-bottom: 2px;">出場時間</div>
            <div style="color: {p['text_primary']}; font-size: 12px; font-family: {p['font_mono']};">{exit_}</div>
        </div>
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: none; letter-spacing: 0; margin-bottom: 2px;">持倉時間</div>
            <div style="color: {p['text_primary']}; font-size: 12px; font-family: {p['font_mono']};">{dur_str}</div>
        </div>
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: none; letter-spacing: 0; margin-bottom: 2px;">出場原因</div>
            <div style="color: {p['text_primary']}; font-size: 12px;">{exit_reason}</div>
        </div>
    </div>
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 12px; padding-top: 12px; border-top: 1px solid {p['border']};">
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: none; letter-spacing: 0; margin-bottom: 2px;">進場價</div>
            <div style="color: {p['text_primary']}; font-size: 14px; font-family: {p['font_mono']};">${entry_price:,.2f}</div>
        </div>
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: none; letter-spacing: 0; margin-bottom: 2px;">出場價</div>
            <div style="color: {p['text_primary']}; font-size: 14px; font-family: {p['font_mono']};">${exit_price:,.2f}</div>
        </div>
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: none; letter-spacing: 0; margin-bottom: 2px;">損益</div>
            <div style="color: {accent}; font-size: 14px; font-weight: 600; font-family: {p['font_mono']};">${pnl:+,.2f}</div>
        </div>
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: none; letter-spacing: 0; margin-bottom: 2px;">報酬率</div>
            <div style="color: {accent}; font-size: 14px; font-weight: 600; font-family: {p['font_mono']};">{pnl_pct:+.2f}%</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


def _resolve_chart_columns(result_df: pd.DataFrame) -> dict:
    """自動偵測並解析圖表需要的欄位。"""
    cols = {}

    if all(c in result_df.columns for c in ["open", "high", "low", "close"]):
        cols["open"] = "open"
        cols["high"] = "high"
        cols["low"] = "low"
        cols["close"] = "close"
        cols["volume"] = "volume" if "volume" in result_df.columns else None
        cols["mode"] = "single"
        return cols

    close_cols = [c for c in result_df.columns if c.endswith("_close")]
    if len(close_cols) >= 1:
        first_sym = close_cols[0].replace("_close", "")
        cols["open"] = f"{first_sym}_open"
        cols["high"] = f"{first_sym}_high"
        cols["low"] = f"{first_sym}_low"
        cols["close"] = f"{first_sym}_close"
        cols["volume"] = f"{first_sym}_volume" if f"{first_sym}_volume" in result_df.columns else None
        cols["symbol"] = first_sym
        cols["mode"] = "pair"
        if len(close_cols) >= 2:
            second_sym = close_cols[1].replace("_close", "")
            cols["symbol2"] = second_sym
            cols["close2"] = f"{second_sym}_close"
        return cols

    return cols


def render_charts(result_df: pd.DataFrame, trades: List[Dict]) -> None:
    """回測 Overview 圖表（TradingView Strategy Tester 風格）。

    v3 重構：完全對齊 TradingView 策略測試器 Overview 視窗
    - 單一繪圖視窗，無子圖結構
    - 兩條核心曲線：策略淨值（主線）+ Buy & Hold 基準（虛線）
    - 策略淨值下方有淡色填滿（TradingView 漸層效果）
    - 線條顏色根據最終盈虧自動切換（綠 = 獲利、紅 = 虧損）
    - Y 軸只有資產淨值（USDT），絕對乾淨
    - 移除所有 K 線、成交量、進出場標記、價格座標軸

    此函式只繪製資產走勢，不再負責交易高亮。
    """
    p = _palette()

    st.markdown(f"""
<div style="
    color: {p['text_secondary']};
    font-size: 11px;
    text-transform: none;
    letter-spacing: 0;
    font-weight: 600;
    margin-bottom: 8px;
    margin-top: 4px;
">資產淨值走勢</div>
""", unsafe_allow_html=True)

    # 守衛：result_df 必須有 equity 欄位
    if result_df is None or not isinstance(result_df, pd.DataFrame) or result_df.empty:
        st.caption("無回測結果資料可顯示")
        return
    if "equity" not in result_df.columns:
        st.caption("缺少 equity 欄位，無法繪製資產走勢")
        return

    # 取淨值序列（直接使用全部資料，不再做 K 線範圍裁切）
    equity = result_df["equity"].dropna()
    if equity.empty:
        st.caption("無有效淨值資料")
        return

    # 初始資金：從第一筆或 metrics 推算（fallback 用首筆當基準）
    initial_capital = float(equity.iloc[0]) if len(equity) > 0 else 10000.0

    # 最終盈虧 → 決定顏色
    final_equity = float(equity.iloc[-1])
    net_profit = final_equity - initial_capital
    is_profit = net_profit >= 0

    # TradingView 配色（與 render_tv_equity_chart 一致）
    tv_green = "#26A69A"
    tv_red = "#EF5350"
    tv_orange = "#FF9800"

    equity_color = tv_green if is_profit else tv_red
    fill_rgba = "rgba(38, 166, 154, 0.12)" if is_profit else "rgba(239, 83, 80, 0.12)"

    # Buy & Hold 基準線（若資料內含 buy_hold 欄位）
    has_buy_hold = "buy_hold" in result_df.columns
    buy_hold_series = result_df["buy_hold"].dropna() if has_buy_hold else None

    # === 單一繪圖視窗（無子圖）===
    fig = go.Figure()

    # 1) 策略淨值下方淡色填滿
    fig.add_trace(go.Scatter(
        x=equity.index,
        y=equity.values,
        mode="lines",
        name="策略淨值",
        line=dict(color=equity_color, width=2.4, shape="spline", smoothing=0.6),
        fill="tozeroy",
        fillcolor=fill_rgba,
        hovertemplate=(
            "<b>%{x|%Y-%m-%d %H:%M}</b><br>"
            "淨值：$%{y:,.2f}<extra></extra>"
        ),
    ))

    # 2) Buy & Hold 基準線（虛線）
    if has_buy_hold and buy_hold_series is not None and not buy_hold_series.empty:
        fig.add_trace(go.Scatter(
            x=buy_hold_series.index,
            y=buy_hold_series.values,
            mode="lines",
            name="Buy & Hold",
            line=dict(color=tv_orange, width=1.4, dash="dash", shape="spline", smoothing=0.6),
            opacity=0.85,
            hovertemplate=(
                "<b>%{x|%Y-%m-%d %H:%M}</b><br>"
                "Buy & Hold：$%{y:,.2f}<extra></extra>"
            ),
        ))

    # 3) 初始資金水平參考線
    fig.add_hline(
        y=initial_capital,
        line=dict(color=p["text_muted"], width=1, dash="dot"),
        opacity=0.5,
        annotation_text=f"初始資金 ${initial_capital:,.0f}",
        annotation_position="right",
        annotation_font=dict(size=10, color=p["text_muted"], family=p["font_mono"]),
    )

    # === Layout（單一視窗、乾淨的 Y 軸）===
    fig.update_layout(
        height=440,
        hovermode="x unified",
        template=get_current_theme()["plotly_template"],
        paper_bgcolor=p["bg"],
        plot_bgcolor=p["bg"],
        font=dict(color=p["text_primary"], family="system-ui", size=12),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11, color=p["text_secondary"]),
        ),
        margin=dict(l=72, r=24, t=12, b=44),
        # 單一 X 軸（無 rangeslider、乾淨）
        xaxis=dict(
            gridcolor=p["border"],
            showgrid=True,
            zeroline=False,
            showline=False,
            tickfont=dict(size=10, color=p["text_muted"], family=p["font_mono"]),
        ),
        # 單一 Y 軸：僅資產淨值
        yaxis=dict(
            gridcolor=p["border"],
            showgrid=True,
            zeroline=False,
            side="left",
            title=dict(text="淨值 (USDT)", font=dict(size=11, color=p["text_secondary"])),
            tickfont=dict(size=10, color=p["text_muted"], family=p["font_mono"]),
            ticks="outside",
            ticklen=4,
            tickcolor=p["border"],
            nticks=6,
            tickformat=",.0s",
            rangemode="normal",
        ),
    )

    # X 軸時間格式（自動）
    try:
        if isinstance(equity.index, pd.DatetimeIndex):
            median_diff = equity.index.to_series().diff().median().total_seconds()
            if median_diff <= 86400 * 3:
                fig.update_xaxes(tickformat="%Y-%m-%d")
            else:
                fig.update_xaxes(tickformat="%Y-%m")
    except Exception:
        pass

    st.plotly_chart(fig, use_container_width=True, config={"staticPlot": True, "displayModeBar": False})


def _max_consecutive(series: pd.Series) -> int:
    """計算最大連續 True 數量。"""
    if series.empty:
        return 0
    max_count = 0
    current = 0
    for val in series:
        if val:
            current += 1
            max_count = max(max_count, current)
        else:
            current = 0
    return max_count


def render_monte_carlo(initial_capital: float, trades: List[Dict]) -> None:
    """蒙地卡羅模擬（保留原版核心 + TradingView 風格 UI）。"""
    p = _palette()

    st.markdown(f"""
<div style="
    color: {p['text_secondary']};
    font-size: 11px;
    text-transform: none;
    letter-spacing: 0;
    font-weight: 600;
    margin-bottom: 8px;
    margin-top: 4px;
">蒙地卡羅模擬</div>
""", unsafe_allow_html=True)

    st.caption("""
    透過**隨機重排交易順序** N 次，模擬「如果未來交易以不同順序發生」的各種可能結果。
    這能幫助您評估策略的**穩健性**——不僅是「賺多少」，更是「在各種情況下表現如何」。
    """)

    if not trades or len(trades) < 5:
        st.warning(" 交易數不足（需要至少 5 筆交易才能進行有意義的蒙地卡羅模擬）")
        return

    # 設定區
    col1, col2, col3 = st.columns(3)
    with col1:
        n_sims = st.number_input("模擬次數", min_value=100, max_value=10000, value=1000, step=100)
    with col2:
        method = st.selectbox("抽樣方法", ["shuffle (重排)", "bootstrap (有放回)"], index=0)
        method_code = "shuffle" if "shuffle" in method else "bootstrap"
    with col3:
        ruin_threshold = st.number_input("破產門檻 (%)", min_value=10, max_value=90, value=50,
                                          help="虧損超過此百分比視為破產")

    if st.button("執行蒙地卡羅模擬", type="primary", use_container_width=True):
        with st.spinner(f"執行 {n_sims} 次模擬中..."):
            from utils.monte_carlo import MonteCarloSimulator
            sim = MonteCarloSimulator(initial_capital=initial_capital)
            mc_results = sim.run(trades, n_simulations=n_sims, method=method_code,
                                  max_loss_pct=ruin_threshold)
            st.session_state["mc_results"] = mc_results

    # 顯示結果
    if "mc_results" in st.session_state and st.session_state["mc_results"]:
        mc = st.session_state["mc_results"]
        if "error" in mc:
            st.error(f" {mc['error']}")
            return

        p_stats = mc["percentiles"]

        st.markdown(f"""
<div style="
    color: {p['text_secondary']};
    font-size: 11px;
    text-transform: none;
    letter-spacing: 0;
    font-weight: 600;
    margin: 20px 0 8px 0;
">模擬結果摘要 ({mc['n_simulations']} 次)</div>
""", unsafe_allow_html=True)

        c1, c2, c3, c4, c5 = st.columns(5)

        median_color = p["green_text"] if p_stats["return_p50"] >= 0 else p["red_text"]
        ruin_color = p["red_text"] if mc["ruin_prob"] > 10 else (
            p["orange"] if mc["ruin_prob"] > 5 else p["green_text"]
        )

        with c1:
            st.markdown(_kpi_card_html(
                "中位數報酬", f"{p_stats['return_p50']:+.2f}%",
                "positive" if p_stats['return_p50'] >= 0 else "negative",
                sub=f"平均 {p_stats['return_mean']:+.2f}%",
            ), unsafe_allow_html=True)
        with c2:
            st.markdown(_kpi_card_html(
                "最壞 5%", f"{p_stats['return_p5']:+.2f}%",
                "negative",
                sub=f"最好 5% {p_stats['return_p95']:+.2f}%",
            ), unsafe_allow_html=True)
        with c3:
            st.markdown(_kpi_card_html(
                "中位數回撤", f"{p_stats['dd_p50']:.2f}%",
                "negative" if p_stats['dd_p50'] > 20 else "neutral",
                sub=f"最壞 5% {p_stats['dd_p95']:.2f}%",
            ), unsafe_allow_html=True)
        with c4:
            st.markdown(_kpi_card_html(
                "破產機率", f"{mc['ruin_prob']:.2f}%",
                "negative" if mc["ruin_prob"] > 10 else ("neutral" if mc["ruin_prob"] > 5 else "positive"),
            ), unsafe_allow_html=True)
        with c5:
            st.markdown(_kpi_card_html(
                "風險調整", f"{p_stats['risk_adj_ratio']:.2f}",
                "positive" if p_stats['risk_adj_ratio'] > 1 else "neutral",
                sub="平均報酬 / 平均回撤",
            ), unsafe_allow_html=True)

        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

        # === 圖表：權益曲線分布 ===
        st.markdown(f"""
<div style="
    font-size: 14px;
    font-weight: 600;
    color: {p['text_primary']};
    margin: 16px 0 8px 0;
">權益曲線分布（隨機路徑）</div>
""", unsafe_allow_html=True)

        equity_curves = mc["equity_curves"]
        n_trades = mc["n_trades"]
        x_axis = list(range(n_trades + 1))
        x_labels = [f"#{i}" for i in x_axis]

        p05 = np.percentile(equity_curves, 5, axis=0)
        p25 = np.percentile(equity_curves, 25, axis=0)
        p50 = np.percentile(equity_curves, 50, axis=0)
        p75 = np.percentile(equity_curves, 75, axis=0)
        p95 = np.percentile(equity_curves, 95, axis=0)

        fig = go.Figure()

        # 5%-95% 區間
        fig.add_trace(go.Scatter(
            x=x_labels + x_labels[::-1],
            y=list(p95) + list(p05[::-1]),
            fill="toself",
            fillcolor="rgba(34, 197, 94, 0.08)",
            line=dict(color="rgba(255,255,255,0)"),
            name="5%-95% 區間",
            showlegend=True,
        ))
        # 25%-75% 區間
        fig.add_trace(go.Scatter(
            x=x_labels + x_labels[::-1],
            y=list(p75) + list(p25[::-1]),
            fill="toself",
            fillcolor="rgba(34, 197, 94, 0.18)",
            line=dict(color="rgba(255,255,255,0)"),
            name="25%-75% 區間",
            showlegend=True,
        ))
        # 中位數
        fig.add_trace(go.Scatter(
            x=x_labels, y=p50,
            mode="lines",
            name="中位數",
            line=dict(color=p["primary"], width=2.5),
        ))

        # 樣本路徑
        n_samples = min(15, mc["n_simulations"])
        sample_indices = np.random.choice(mc["n_simulations"], n_samples, replace=False)
        for idx in sample_indices:
            fig.add_trace(go.Scatter(
                x=x_labels, y=equity_curves[idx],
                mode="lines",
                line=dict(color="rgba(100, 116, 139, 0.15)", width=0.5),
                showlegend=False,
                hoverinfo="skip",
            ))

        fig.add_hline(
            y=initial_capital,
            line_dash="dash",
            line_color=p["text_muted"],
            annotation_text=f"初始資金 ${initial_capital:,.0f}",
            annotation_position="right",
        )

        fig.update_layout(
            height=420,
            template=get_current_theme()["plotly_template"],
            paper_bgcolor=p["bg"],
            plot_bgcolor=p["bg"],
            font=dict(color=p["text_primary"], family="system-ui", size=12),
            hovermode="x unified",
            xaxis_title="交易編號",
            yaxis_title="權益 (USDT)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=60, r=24, t=24, b=40),
            xaxis=dict(gridcolor=p["border"], zeroline=False),
            yaxis=dict(gridcolor=p["border"], zeroline=False),
        )
        st.plotly_chart(fig, use_container_width=True, config={"staticPlot": True, "displayModeBar": False})

        # === 雙直方圖：報酬率 & 回撤分布 ===
        st.markdown(f"""
<div style="
    font-size: 14px;
    font-weight: 600;
    color: {p['text_primary']};
    margin: 16px 0 8px 0;
">最終報酬率 &amp; 最大回撤分布</div>
""", unsafe_allow_html=True)

        col1, col2 = st.columns(2)

        with col1:
            fig_ret = go.Figure()
            fig_ret.add_trace(go.Histogram(
                x=mc["final_returns"],
                nbinsx=50,
                marker_color=p["primary"],
                marker_line_color="white",
                marker_line_width=1,
                opacity=0.85,
                name="報酬率",
            ))
            fig_ret.add_vline(
                x=p_stats["return_p50"],
                line_dash="dash",
                line_color=p["red"],
                annotation_text=f"中位數 {p_stats['return_p50']:+.1f}%",
                annotation_position="top",
            )
            fig_ret.add_vline(
                x=p_stats["return_mean"],
                line_dash="dot",
                line_color=p["green"],
                annotation_text=f"平均 {p_stats['return_mean']:+.1f}%",
                annotation_position="bottom",
            )
            fig_ret.update_layout(
                height=320,
                template=get_current_theme()["plotly_template"],
                paper_bgcolor=p["bg"],
                plot_bgcolor=p["bg"],
                font=dict(color=p["text_primary"], family="system-ui", size=12),
                xaxis_title="最終報酬率 (%)",
                yaxis_title="模擬次數",
                showlegend=False,
                margin=dict(l=60, r=24, t=24, b=40),
                xaxis=dict(gridcolor=p["border"], zeroline=False),
                yaxis=dict(gridcolor=p["border"], zeroline=False),
            )
            st.plotly_chart(fig_ret, use_container_width=True, config={"staticPlot": True, "displayModeBar": False})

        with col2:
            fig_dd = go.Figure()
            fig_dd.add_trace(go.Histogram(
                x=mc["max_drawdowns"],
                nbinsx=50,
                marker_color=p["red"],
                marker_line_color="white",
                marker_line_width=1,
                opacity=0.85,
                name="回撤",
            ))
            fig_dd.add_vline(
                x=p_stats["dd_p50"],
                line_dash="dash",
                line_color=p["blue"] if "blue" in p else p["primary"],
                annotation_text=f"中位數 {p_stats['dd_p50']:.1f}%",
                annotation_position="top",
            )
            fig_dd.add_vline(
                x=p_stats["dd_p95"],
                line_dash="dot",
                line_color=p["orange"],
                annotation_text=f"最壞 5% {p_stats['dd_p95']:.1f}%",
                annotation_position="bottom",
            )
            fig_dd.update_layout(
                height=320,
                template=get_current_theme()["plotly_template"],
                paper_bgcolor=p["bg"],
                plot_bgcolor=p["bg"],
                font=dict(color=p["text_primary"], family="system-ui", size=12),
                xaxis_title="最大回撤 (%)",
                yaxis_title="模擬次數",
                showlegend=False,
                margin=dict(l=60, r=24, t=24, b=40),
                xaxis=dict(gridcolor=p["border"], zeroline=False),
                yaxis=dict(gridcolor=p["border"], zeroline=False),
            )
            st.plotly_chart(fig_dd, use_container_width=True, config={"staticPlot": True, "displayModeBar": False})

        # === 風險評估總結 ===
        st.markdown(f"""
<div style="
    font-size: 14px;
    font-weight: 600;
    color: {p['text_primary']};
    margin: 16px 0 8px 0;
">風險評估總結</div>
""", unsafe_allow_html=True)

        if mc["ruin_prob"] > 20:
            risk_level = "高風險"
            risk_msg = "破產機率過高（>20%），強烈建議重新設計策略或降低倉位。"
        elif mc["ruin_prob"] > 10:
            risk_level = "中風險"
            risk_msg = "存在一定風險，建議謹慎使用，考慮加入倉位管理。"
        elif p_stats["dd_p95"] > 40:
            risk_level = "需注意"
            risk_msg = "破產機率低，但最壞情況回撤可能較大，請做好風險控制。"
        elif p_stats["return_p5"] > 0:
            risk_level = "低風險"
            risk_msg = "在 95% 信心區間下仍然獲利，策略非常穩健。"
        else:
            risk_level = "觀察中"
            risk_msg = "整體正向但有風險，建議結合其他指標綜合評估。"

        st.markdown(f"""
<div style="
    background: {p['bg_subtle']};
    padding: 18px 22px;
    border-radius: 8px;
    border: 1px solid {p['border']};
    margin-top: 8px;
">
    <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 10px;">
        <div style="color: {p['text_secondary']}; font-size: 13px;">風險等級</div>
        <div style="font-size: 15px; font-weight: 600;">{risk_level}</div>
    </div>
    <div style="color: {p['text_primary']}; font-size: 13px; line-height: 1.6;">
        {risk_msg}
    </div>
    <div style="color: {p['text_secondary']}; font-size: 11px; margin-top: 10px; padding-top: 10px; border-top: 1px solid {p['border']};">
        詳細數據：中位數 {p_stats['return_p50']:+.2f}% · 平均 {p_stats['return_mean']:+.2f}% · 標準差 {p_stats['return_std']:.2f}% ·
        最壞 5% {p_stats['return_p5']:+.2f}% · 最好 5% {p_stats['return_p95']:+.2f}% ·
        中位數回撤 {p_stats['dd_p50']:.2f}% · 最壞 5% 回撤 {p_stats['dd_p95']:.2f}%
    </div>
</div>
""", unsafe_allow_html=True)
