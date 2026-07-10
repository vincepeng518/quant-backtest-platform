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
        "bg": t["bg"],
        "bg_subtle": t["bg_subtle"],
        "bg_card": t["bg_card"],
        "border": t["border"],
        "border_strong": t["border_strong"],
        "text_primary": t["text_primary"],
        "text_secondary": t["text_secondary"],
        "text_muted": t["text_muted"],
        "primary": t["primary"],
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
    }


# === TradingView 風格 KPI 卡片列 ===
def _kpi_card_html(
    label: str,
    value: str,
    sentiment: str = "neutral",  # 'positive' | 'negative' | 'neutral'
    sub: str = "",
) -> str:
    """單個 TradingView 風格的 KPI 卡。"""
    p = _palette()
    if sentiment == "positive":
        accent = p["green_text"]
    elif sentiment == "negative":
        accent = p["red_text"]
    else:
        accent = p["text_primary"]

    # 結構：3 個 div 區塊（label / value / sub），用普通字符串拼接避免 f-string 嵌套 escape
    sub_block = ""
    if sub:
        sub_color = p["text_muted"]
        if sub.startswith("+"):
            sub_color = p["green_text"]
        elif sub.startswith("-"):
            sub_color = p["red_text"]
        sub_block = (
            '<div style="color: ' + sub_color + '; font-size: 11px; margin-top: 4px; font-weight: 500;">'
            + sub +
            '</div>'
        )

    # 用字符串拼接而非 f-string 嵌入 sub_block
    card_html = (
        '<div style="'
        'background: ' + p["bg_card"] + '; '
        'border: 1px solid ' + p["border"] + '; '
        'border-radius: 8px; '
        'padding: 12px 16px; '
        'min-height: 78px; '
        'display: flex; '
        'flex-direction: column; '
        'justify-content: space-between;'
        '">'
        '<div style="'
        'color: ' + p["text_secondary"] + '; '
        'font-size: 11px; '
        'text-transform: uppercase; '
        'letter-spacing: 0.06em; '
        'font-weight: 500;'
        '">' + label + '</div>'
        '<div style="margin-top: 6px;">'
        '<div style="'
        'color: ' + accent + '; '
        'font-family: ' + p["font_mono"] + '; '
        'font-size: 22px; '
        'font-weight: 600; '
        'line-height: 1.1;'
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

    # 雙子圖（主圖 70% + Drawdown 30%）
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.70, 0.30],
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
            hovertemplate="<b>%{x|%Y-%m-%d %H:%M}</b><br>權益：$%{y:,.2f}<extra></extra>",
        ),
        row=1, col=1,
    )

    # Buy & Hold 基準
    if "buy_hold" in result_df.columns:
        fig.add_trace(
            go.Scatter(
                x=result_df.index,
                y=result_df["buy_hold"],
                name="Buy &amp; Hold",
                mode="lines",
                line=dict(color=p["orange"], width=1.5, dash="dash"),
                opacity=0.8,
                hovertemplate="<b>%{x|%Y-%m-%d %H:%M}</b><br>Buy &amp; Hold：$%{y:,.2f}<extra></extra>",
            ),
            row=1, col=1,
        )

    # Drawdown 子圖
    fig.add_trace(
        go.Scatter(
            x=result_df.index,
            y=drawdown_pct,
            name="回撤 %",
            mode="lines",
            line=dict(color=p["red"], width=1),
            fill="tozeroy",
            fillcolor="rgba(239, 68, 68, 0.15)",
            hovertemplate="<b>%{x|%Y-%m-%d %H:%M}</b><br>回撤：%{y:.2f}%<extra></extra>",
        ),
        row=2, col=1,
    )

    # Layout
    fig.update_layout(
        height=520,
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
            font=dict(size=12),
        ),
        margin=dict(l=60, r=24, t=24, b=40),
        xaxis=dict(gridcolor=p["border"], showgrid=True, zeroline=False, rangeslider=dict(visible=False)),
        xaxis2=dict(gridcolor=p["border"], showgrid=False, zeroline=False),
        yaxis=dict(
            gridcolor=p["border"],
            showgrid=True,
            zeroline=False,
            title=dict(text="權益 (USDT)", font=dict(size=11, color=p["text_secondary"])),
            side="left",
        ),
        yaxis2=dict(
            gridcolor=p["border"],
            showgrid=True,
            zeroline=False,
            title=dict(text="回撤 (%)", font=dict(size=11, color=p["text_secondary"])),
            side="left",
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

    st.plotly_chart(fig, use_container_width=True)


def _tv_kpi_card_html(
    label: str,
    value: str,
    sub: str = "",
    sub_color: str = None,
    icon_svg: str = "",
    tooltip: str = "",
) -> str:
    """TradingView 風格單個 KPI 卡（極簡，無 sentiment 顏色編碼）。

    設計參考 TradingView Strategy Tester：
    - 標題小寫灰字
    - 數值大，monospace
    - 副標題小字（百分比變化紅綠）
    - 右上角 ? tooltip icon（optional）
    """
    p = _palette()
    if sub_color is None:
        sub_color = p["text_muted"]
    info_icon = ""
    if tooltip:
        info_icon = (
            '<span style="color: ' + p["text_muted"] + '; margin-left: 4px; font-size: 12px; cursor: help;" '
            'title="' + tooltip + '">ⓘ</span>'
        )
    sub_block = ""
    if sub:
        sub_block = (
            '<div style="color: ' + sub_color + '; font-size: 11px; margin-top: 2px; font-weight: 500;">'
            + sub + '</div>'
        )
    # 主卡片結構
    return (
        '<div style="'
        'background: ' + p["bg_card"] + '; '
        'border: 1px solid ' + p["border"] + '; '
        'border-radius: 6px; '
        'padding: 14px 18px; '
        'min-height: 72px;'
        '">'
        '<div style="'
        'color: ' + p["text_secondary"] + '; '
        'font-size: 11px; '
        'font-weight: 500; '
        'display: flex; '
        'align-items: center; '
        'justify-content: space-between;'
        '">'
        '<span>' + label + '</span>'
        + info_icon +
        '</div>'
        '<div style="'
        'color: ' + p["text_primary"] + '; '
        'font-family: ' + p["font_mono"] + '; '
        'font-size: 22px; '
        'font-weight: 600; '
        'line-height: 1.2; '
        'margin-top: 6px;'
        '">' + value + '</div>'
        + sub_block +
        '</div>'
    )


def render_tv_overview(
    metrics: Dict,
    result_df: pd.DataFrame,
    initial_capital: float,
) -> None:
    """TradingView Strategy Tester 風格的 Overview 頁面。

    結構（與截圖一致）：
    ┌─ Strategy Backtest Report 標題列（含 Buy & Hold toggle、Absolute/Percent toggle）┐
    ├─ 5 大核心 KPI 卡片列（Total P&L / Max Drawdown / Total Trades / Profitable / Profit Factor）┤
    ├─ 6 個次要 KPI 卡片列（Buy & Hold / Sharpe / Calmar / CAGR / Sortino / Recovery）┤
    ├─ 主圖：權益曲線 + Buy & Hold + Drawdown 子圖┤
    ├─ 交易統計 4×3 網格 KPI┤
    """
    p = _palette()

    # === 數據準備 ===
    metrics_with_cap = {**metrics, "initial_capital": initial_capital}
    total_return = metrics.get("total_return_pct", 0)
    final_equity = metrics.get("final_equity", initial_capital)
    net_profit = final_equity - initial_capital
    max_dd = metrics.get("max_drawdown_pct", 0)
    max_dd_amount = initial_capital * abs(max_dd) / 100 if max_dd else 0
    win_rate = metrics.get("win_rate", 0)
    n_trades = metrics.get("n_trades", 0)
    sharpe = metrics.get("sharpe_ratio", 0)
    profit_factor = metrics.get("profit_factor", 0)
    buy_hold = metrics.get("buy_hold_return_pct", 0)
    avg_win = metrics.get("avg_win_pct", 0)
    avg_loss = metrics.get("avg_loss_pct", 0)
    n_wins = int(n_trades * win_rate / 100) if n_trades > 0 else 0

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
        # Buy & Hold toggle（checkbox）— 在 chart 渲染前設定，這樣下面 _render_tv_equity_chart 才讀得到
        st.markdown(f"""
<div style="display: flex; gap: 8px; align-items: center; justify-content: flex-end; margin-top: 16px;">
    <label style="display: flex; align-items: center; gap: 6px; color: {p['orange']};
                  font-size: 12px; font-weight: 500; cursor: pointer;
                  padding: 4px 10px; border: 1px solid {p['border']}; border-radius: 4px;
                  background: {p['bg_card']};">
        <input type="checkbox" id="bh-toggle-tv" {'checked' if st.session_state['show_buy_hold'] else ''}
               style="accent-color: {p['orange']}; cursor: pointer;"/>
        Buy &amp; hold
    </label>
</div>
""", unsafe_allow_html=True)

        # 用 st.checkbox 觸發 session_state 更新
        st.session_state["show_buy_hold"] = st.checkbox(
            "Buy & hold 線",
            value=st.session_state["show_buy_hold"],
            key="tv_show_buy_hold",
            label_visibility="collapsed",
        )

        # 絕對/百分比 toggle
        cur_abs = st.session_state["show_absolute"]
        st.markdown(f"""
<div style="display: inline-flex; border: 1px solid {p['border']}; border-radius: 4px;
            overflow: hidden; font-size: 12px; margin-left: 6px;">
    <button id="abs-btn-tv" style="padding: 4px 12px; background: {p['primary'] if cur_abs else p['bg_subtle']};
            color: {('white' if cur_abs else p['text_secondary'])}; font-weight: 600; border: none;
            cursor: pointer;">Absolute</button>
    <button id="pct-btn-tv" style="padding: 4px 12px; background: {p['bg_subtle'] if cur_abs else p['primary']};
            color: {p['text_secondary'] if cur_abs else 'white'}; font-weight: 600; border: none;
            cursor: pointer;">Percentage</button>
</div>
""", unsafe_allow_html=True)
        # 簡化：兩個 radio button 在 col 內（用 st.radio）
        abs_val = st.radio(
            "Display unit",
            options=["Absolute", "Percentage"],
            index=0 if cur_abs else 1,
            key="tv_show_absolute",
            label_visibility="collapsed",
            horizontal=True,
        )
        st.session_state["show_absolute"] = (abs_val == "Absolute")

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
            tooltip="總損益金額與百分比",
        ), unsafe_allow_html=True)
    with k2:
        st.markdown(_tv_kpi_card_html(
            "Max equity drawdown",
            f"<span style='color: {p['red_text']};'>${max_dd_amount:,.2f}</span>",
            sub=f"<span style='color: {p['red_text']};'>{max_dd:.2f}%</span>",
            tooltip="歷史最大資金回撤",
        ), unsafe_allow_html=True)
    with k3:
        st.markdown(_tv_kpi_card_html(
            "Total trades",
            f"{n_trades:,}",
            sub="<span style='color: " + p["text_muted"] + ";'>全部交易</span>",
            tooltip="策略執行的總交易次數",
        ), unsafe_allow_html=True)
    with k4:
        win_color = p["green_text"] if win_rate >= 50 else p["red_text"]
        st.markdown(_tv_kpi_card_html(
            "Profitable trades",
            f"{n_wins:,}<span style='color: {p['text_muted']}; font-size: 16px;'>/{n_trades:,}</span>",
            sub=f"<span style='color: {win_color};'>{win_rate:.2f}%</span>",
            tooltip="獲利交易數 / 總交易數 / 勝率",
        ), unsafe_allow_html=True)
    with k5:
        pf_str = f"{profit_factor:.3f}" if np.isfinite(profit_factor) else "∞"
        pf_color = p["green_text"] if profit_factor > 1.5 else (p["text_primary"] if profit_factor > 1 else p["red_text"])
        st.markdown(_tv_kpi_card_html(
            "Profit factor",
            f"<span style='color: {pf_color};'>{pf_str}</span>",
            sub="<span style='color: " + p["text_muted"] + ";'>毛利 / 毛損</span>",
            tooltip="總獲利 / 總虧損（>1 為獲利策略）",
        ), unsafe_allow_html=True)

    # === 3. 次要 6 指標列 ===
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    with k1:
        bh_color = p["green_text"] if buy_hold >= 0 else p["red_text"]
        st.markdown(_tv_kpi_card_html(
            "Buy &amp; Hold",
            f"<span style='color: {bh_color};'>{buy_hold:+.2f}%</span>",
            sub="<span style='color: " + p["text_muted"] + ";'>基準報酬</span>",
        ), unsafe_allow_html=True)
    with k2:
        alpha = total_return - buy_hold
        a_color = p["green_text"] if alpha > 0 else p["red_text"]
        st.markdown(_tv_kpi_card_html(
            "α 超額報酬",
            f"<span style='color: {a_color};'>{alpha:+.2f}%</span>",
            sub="<span style='color: " + p["text_muted"] + ";'>策略 - B&H</span>",
        ), unsafe_allow_html=True)
    with k3:
        sh_color = p["green_text"] if sharpe > 1 else (p["text_primary"] if sharpe > 0 else p["red_text"])
        st.markdown(_tv_kpi_card_html(
            "Sharpe",
            f"<span style='color: {sh_color};'>{sharpe:.2f}</span>",
            sub="<span style='color: " + p["text_muted"] + ";'>風險調整報酬</span>",
        ), unsafe_allow_html=True)
    with k4:
        so_color = p["green_text"] if sortino > 1 else (p["text_primary"] if sortino > 0 else p["red_text"])
        st.markdown(_tv_kpi_card_html(
            "Sortino",
            f"<span style='color: {so_color};'>{sortino:.2f}</span>",
            sub="<span style='color: " + p["text_muted"] + ";'>下行風險調整</span>",
        ), unsafe_allow_html=True)
    with k5:
        ca_color = p["green_text"] if cagr >= 0 else p["red_text"]
        st.markdown(_tv_kpi_card_html(
            "CAGR",
            f"<span style='color: {ca_color};'>{cagr:+.2f}%</span>",
            sub="<span style='color: " + p["text_muted"] + ";'>年化報酬</span>",
        ), unsafe_allow_html=True)
    with k6:
        cm_color = p["green_text"] if calmar > 1 else (p["text_primary"] if calmar > 0 else p["red_text"])
        st.markdown(_tv_kpi_card_html(
            "Calmar",
            f"<span style='color: {cm_color};'>{calmar:.2f}</span>",
            sub="<span style='color: " + p["text_muted"] + ";'>CAGR / MaxDD</span>",
        ), unsafe_allow_html=True)

    # === 4. 主圖：權益曲線 + Buy & Hold + Drawdown（TradingView 風格）===
    st.markdown(f"""
<div style="
    color: {p['text_secondary']};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
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
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
    margin: 28px 0 8px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid {p['border']};
">Trade Statistics</div>
""", unsafe_allow_html=True)

    _render_trade_stats_grid(metrics, n_trades, n_wins, win_rate, profit_factor, avg_win, avg_loss, rr, recovery, p)


def _render_tv_equity_chart(result_df: pd.DataFrame, metrics: Dict, show_buy_hold: bool = True) -> None:
    """TradingView 風格主圖（權益 + Drawdown）— 比 render_equity_chart 更 TV 化。"""
    p = _palette()
    initial_capital = metrics.get("initial_capital", 10000)
    net_profit = metrics.get("final_equity", initial_capital) - initial_capital
    is_profit = net_profit >= 0

    equity_color = p["green"] if is_profit else p["red"]
    fill_rgba = "rgba(34, 197, 94, 0.10)" if is_profit else "rgba(239, 68, 68, 0.10)"

    equity = result_df["equity"]
    cummax = equity.cummax()
    drawdown_pct = (equity - cummax) / cummax * 100

    # === 主圖 + Drawdown 子圖（70% / 30%）===
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.72, 0.28],
    )

    # 1. 策略權益曲線（粗線 + 填充）
    fig.add_trace(go.Scatter(
        x=result_df.index,
        y=equity,
        name="策略",
        mode="lines",
        line=dict(color=equity_color, width=2.2),
        fill="tozeroy",
        fillcolor=fill_rgba,
        hovertemplate="<b>%{x|%Y-%m-%d %H:%M}</b><br>策略權益：$%{y:,.2f}<extra></extra>",
    ), row=1, col=1)

    # 2. Buy & Hold 基準線（虛線）
    if show_buy_hold and "buy_hold" in result_df.columns:
        fig.add_trace(go.Scatter(
            x=result_df.index,
            y=result_df["buy_hold"],
            name="Buy &amp; Hold",
            mode="lines",
            line=dict(color=p["orange"], width=1.3, dash="dash"),
            opacity=0.85,
            hovertemplate="<b>%{x|%Y-%m-%d %H:%M}</b><br>Buy &amp; Hold：$%{y:,.2f}<extra></extra>",
        ), row=1, col=1)

    # 3. 進場做多 marker（綠色向上三角）
    if "entry" in result_df.columns and "position" in result_df.columns:
        long_mask = result_df["entry"] & (result_df["position"] == 1)
        long_entries = result_df[long_mask]
        if not long_entries.empty:
            close_col = "close" if "close" in result_df.columns else "equity"
            fig.add_trace(go.Scatter(
                x=long_entries.index,
                y=long_entries[close_col] if close_col in long_entries.columns else long_entries["equity"],
                mode="markers",
                name="做多進場",
                marker=dict(
                    symbol="triangle-up",
                    size=8,
                    color=p["green"],
                    line=dict(color="white", width=1),
                ),
                hovertemplate="<b>%{x|%Y-%m-%d}</b><br>做多進場<br>價：$%{y:,.2f}<extra></extra>",
            ), row=1, col=1)

        # 4. 進場做空 marker（紅色向下三角）
        short_mask = result_df["entry"] & (result_df["position"] == -1)
        short_entries = result_df[short_mask]
        if not short_entries.empty:
            fig.add_trace(go.Scatter(
                x=short_entries.index,
                y=short_entries[close_col] if close_col in short_entries.columns else short_entries["equity"],
                mode="markers",
                name="做空進場",
                marker=dict(
                    symbol="triangle-down",
                    size=8,
                    color=p["red"],
                    line=dict(color="white", width=1),
                ),
                hovertemplate="<b>%{x|%Y-%m-%d}</b><br>做空進場<br>價：$%{y:,.2f}<extra></extra>",
            ), row=1, col=1)

    # 5. 出場 marker（橙色叉）
    if "exit" in result_df.columns:
        exits = result_df[result_df["exit"]]
        if not exits.empty:
            fig.add_trace(go.Scatter(
                x=exits.index,
                y=exits[close_col] if close_col in exits.columns else exits["equity"],
                mode="markers",
                name="出場",
                marker=dict(
                    symbol="x-thin",
                    size=8,
                    color=p["orange"],
                    line=dict(color=p["orange"], width=2),
                ),
                hovertemplate="<b>%{x|%Y-%m-%d}</b><br>出場<br>價：$%{y:,.2f}<extra></extra>",
            ), row=1, col=1)

    # 6. Drawdown 子圖（紅色面積）
    fig.add_trace(go.Scatter(
        x=result_df.index,
        y=drawdown_pct,
        name="回撤",
        mode="lines",
        line=dict(color=p["red"], width=1, shape="linear"),
        fill="tozeroy",
        fillcolor="rgba(239, 68, 68, 0.15)",
        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>回撤：%{y:.2f}%<extra></extra>",
    ), row=2, col=1)

    # === Layout（TradingView 風格）===
    fig.update_layout(
        height=540,
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
            font=dict(size=11, color=p["text_secondary"]),
        ),
        margin=dict(l=70, r=24, t=8, b=40),
        xaxis=dict(
            gridcolor=p["border"],
            showgrid=True,
            zeroline=False,
            rangeslider=dict(visible=False),
            showline=False,
        ),
        xaxis2=dict(
            gridcolor=p["border"],
            showgrid=False,
            zeroline=False,
        ),
        yaxis=dict(
            gridcolor=p["border"],
            showgrid=True,
            zeroline=False,
            side="left",
            title=None,
            tickfont=dict(size=11, color=p["text_secondary"], family=p["font_mono"]),
        ),
        yaxis2=dict(
            gridcolor=p["border"],
            showgrid=True,
            zeroline=False,
            side="left",
            title=None,
            tickfont=dict(size=10, color=p["text_muted"], family=p["font_mono"]),
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

    st.plotly_chart(fig, use_container_width=True)


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
def render_overview(metrics: Dict, result_df: pd.DataFrame, initial_capital: float) -> None:
    """TradingView Strategy Tester 風格 Overview。"""
    # v4+ 改為 TradingView 風格（重設計）
    render_tv_overview(metrics, result_df, initial_capital)


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
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
    margin: 32px 0 8px 0;
    padding-bottom: 8px;
    border-bottom: 1px solid {p['border']};
">月報酬熱圖</div>
""", unsafe_allow_html=True)

    render_monthly_heatmap(trades_df, p)


def render_monthly_heatmap(trades_df: pd.DataFrame, p: dict) -> None:
    """月報酬熱圖（TradingView 風格）。

    X 軸：年（2014、2015、…）
    Y 軸：月（Jan-Dec）
    Cell：該月報酬 %（綠正 / 紅負）
    """
    if trades_df.empty or "exit_time" not in trades_df.columns:
        st.caption("無交易記錄或缺少 exit_time 欄位")
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
    trades_df["year"] = trades_df["exit_time"].dt.year
    trades_df["month"] = trades_df["exit_time"].dt.month
    monthly_pnl = trades_df.groupby(["year", "month"])["pnl"].sum().reset_index()

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
    st.plotly_chart(fig, use_container_width=True)

    # 熱圖下方：年度總報酬摘要
    yearly_summary = trades_df.groupby("year")["pnl"].sum().reset_index()
    yearly_summary["return_pct"] = (yearly_summary["pnl"] / initial_capital) * 100
    yearly_summary.columns = ["年度", "總損益 (USDT)", "年度報酬 %"]

    st.markdown(f"""
<div style="
    color: {p['text_secondary']};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
    margin: 16px 0 8px 0;
">年度總覽</div>
""", unsafe_allow_html=True)

    # 3 欄：今年度、上年度、平均
    if len(yearly_summary) > 0:
        c1, c2, c3 = st.columns(3)
        with c1:
            latest = yearly_summary.iloc[-1]
            st.markdown(_kpi_card_html(
                f"{int(latest['年度'])} 年度",
                f"${latest['總損益 (USDT)']:+,.0f}",
                "positive" if latest['總損益 (USDT)'] > 0 else "negative",
                sub=f"{latest['年度報酬 %']:+.2f}%",
            ), unsafe_allow_html=True)
        with c2:
            avg = yearly_summary["年度報酬 %"].mean()
            st.markdown(_kpi_card_html(
                "歷年平均",
                f"{avg:+.2f}%",
                "positive" if avg > 0 else "negative",
                sub=f"{len(yearly_summary)} 年",
            ), unsafe_allow_html=True)
        with c3:
            best = yearly_summary.loc[yearly_summary["年度報酬 %"].idxmax()]
            st.markdown(_kpi_card_html(
                f"最佳年度 ({int(best['年度'])})",
                f"${best['總損益 (USDT)']:+,.0f}",
                "positive",
                sub=f"{best['年度報酬 %']:+.2f}%",
            ), unsafe_allow_html=True)


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
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
    margin-bottom: 8px;
    margin-top: 4px;
">交易明細 ({len(trades_df_display)} 筆)</div>
""", unsafe_allow_html=True)

    # v2: 用 streamlit-aggrid 支援 row click → 圖表高亮
    st.caption("提示：點擊任一交易，圖表會自動顯示該交易的進出場位置與損益")

    from st_aggrid import AgGrid, GridOptionsBuilder, JsCode, GridUpdateMode
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
<div style="
    margin-top: 12px;
    padding: 10px 14px;
    background: {p['bg_subtle']};
    border: 1px dashed {p['border']};
    border-radius: 6px;
    color: {p['text_muted']};
    font-size: 12px;
    text-align: center;
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
    border-left: 3px solid {accent};
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
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px;">進場時間</div>
            <div style="color: {p['text_primary']}; font-size: 12px; font-family: {p['font_mono']};">{entry}</div>
        </div>
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px;">出場時間</div>
            <div style="color: {p['text_primary']}; font-size: 12px; font-family: {p['font_mono']};">{exit_}</div>
        </div>
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px;">持倉時間</div>
            <div style="color: {p['text_primary']}; font-size: 12px; font-family: {p['font_mono']};">{dur_str}</div>
        </div>
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px;">出場原因</div>
            <div style="color: {p['text_primary']}; font-size: 12px;">{exit_reason}</div>
        </div>
    </div>
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 12px; padding-top: 12px; border-top: 1px solid {p['border']};">
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px;">進場價</div>
            <div style="color: {p['text_primary']}; font-size: 14px; font-family: {p['font_mono']};">${entry_price:,.2f}</div>
        </div>
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px;">出場價</div>
            <div style="color: {p['text_primary']}; font-size: 14px; font-family: {p['font_mono']};">${exit_price:,.2f}</div>
        </div>
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px;">損益</div>
            <div style="color: {accent}; font-size: 14px; font-weight: 600; font-family: {p['font_mono']};">${pnl:+,.2f}</div>
        </div>
        <div>
            <div style="color: {p['text_muted']}; font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px;">報酬率</div>
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
    """價格走勢圖（TradingView 風格 K 線 + Volume + v2 高亮選中交易）。"""
    import streamlit as st_lib
    p = _palette()

    # 讀取選中交易索引
    selected_idx = st_lib.session_state.get("selected_trade_row")

    st.markdown(f"""
<div style="
    color: {p['text_secondary']};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
    margin-bottom: 8px;
    margin-top: 4px;
">價格走勢 + 進出場標記</div>
""", unsafe_allow_html=True)

    # v2: 顯示選中交易的高亮提示
    if selected_idx is not None and 0 <= selected_idx < len(trades):
        sel_trade = trades[selected_idx]
        dir_label = "做多" if sel_trade.get("direction") == "long" else "做空"
        pnl = sel_trade.get("pnl", 0)
        pnl_pct = sel_trade.get("pnl_pct", 0) * 100
        accent = p["green_text"] if pnl >= 0 else p["red_text"]
        st.markdown(f"""
<div style="
    margin-bottom: 8px;
    padding: 8px 14px;
    background: {p['bg_subtle']};
    border: 1px solid {p['border']};
    border-left: 3px solid {accent};
    border-radius: 4px;
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 12px;
    flex-wrap: wrap;
">
    <span style="color: {p['text_secondary']};">高亮交易</span>
    <span style="color: {p['text_primary']}; font-weight: 600;">#{selected_idx + 1}</span>
    <span style="color: {p['text_secondary']};">·</span>
    <span style="color: {p['text_primary']};">{dir_label}</span>
    <span style="color: {p['text_secondary']};">·</span>
    <span style="color: {accent}; font-weight: 600; font-family: {p['font_mono']};">{pnl_pct:+.2f}% (${pnl:+,.2f})</span>
    <span style="color: {p['text_secondary']};">·</span>
    <span style="color: {p['text_muted']}; font-family: {p['font_mono']};">{sel_trade.get('entry_time', '')}</span>
    <span style="margin-left: auto; display: flex; gap: 6px;">
        <span style="color: {p['text_muted']}; font-size: 10px; padding: 2px 6px;
                     background: {p['bg']}; border-radius: 3px;">
            提示：點 vline 跳回明細
        </span>
        <button onclick="window.parent.st_lib = window.parent.st_lib || {{}};
                window.parent.st_lib.clear_sel = function() {{
                    // 透過 streamlit 自訂事件通知
                    var evt = new CustomEvent('clear-trade-selection', {{ bubbles: true }});
                    window.parent.document.body.dispatchEvent(evt);
                }};
                window.parent.document.body.dispatchEvent(new CustomEvent('clear-trade-selection', {{ bubbles: true }}));
                // 重新刷新頁面（清空 session_state）
                window.parent.location.reload();
            "
            style="
                background: transparent;
                border: 1px solid {p['border_strong']};
                color: {p['text_secondary']};
                font-size: 11px;
                padding: 2px 10px;
                border-radius: 4px;
                cursor: pointer;
            ">清除選擇</button>
    </span>
</div>
""", unsafe_allow_html=True)

    col_map = _resolve_chart_columns(result_df)
    if not col_map:
        st.error("❌ 找不到價格欄位（open/high/low/close）")
        st.info("請確認您的回測資料有正確的 OHLC 欄位")
        return

    display_n = st.slider("顯示最近 N 根 K 線", min_value=50, max_value=min(1000, len(result_df)),
                            value=min(200, len(result_df)), step=50)
    # v3: 如果選了交易，確保進出場時間在顯示範圍內
    display_df = result_df.tail(display_n).copy()  # 預設
    if selected_idx is not None and 0 <= selected_idx < len(trades):
        sel = trades[selected_idx]
        for t_key in ("entry_time", "exit_time"):
            t = sel.get(t_key)
            if t is None or pd.isna(t):
                continue
            t_ts = pd.Timestamp(t)
            if t_ts not in result_df.index:
                continue
            # 找到 t_ts 在 result_df 中的位置
            try:
                pos = result_df.index.get_loc(t_ts)
            except Exception:
                continue
            # 確保 t_ts 在 display_df 範圍：以 t_ts 為中心
            start = max(0, pos - display_n // 2)
            end = min(len(result_df), start + display_n)
            start = max(0, end - display_n)
            display_df = result_df.iloc[start:end].copy()
            break

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.75, 0.25],
        subplot_titles=("", "成交量"),
    )

    candlestick_kwargs = {
        "x": display_df.index,
        "open": display_df[col_map["open"]],
        "high": display_df[col_map["high"]],
        "low": display_df[col_map["low"]],
        "close": display_df[col_map["close"]],
        "increasing_line_color": p["green"],
        "decreasing_line_color": p["red"],
        "increasing_fillcolor": p["green"],
        "decreasing_fillcolor": p["red"],
        "name": col_map.get("symbol", "K 線"),
    }
    fig.add_trace(go.Candlestick(**candlestick_kwargs), row=1, col=1)

    if col_map.get("mode") == "pair" and "close2" in col_map:
        fig.add_trace(
            go.Scatter(
                x=display_df.index, y=display_df[col_map["close2"]],
                name=f"{col_map['symbol2']} 價格",
                line=dict(color=p["orange"], width=1.5, dash="dot"),
                opacity=0.6,
            ),
            row=1, col=1,
        )

    entries_in_view = display_df[display_df["entry"]] if "entry" in display_df.columns else pd.DataFrame()
    if not entries_in_view.empty:
        if "position" in display_df.columns:
            long_entries = entries_in_view[display_df.loc[entries_in_view.index, "position"] == 1]
            short_entries = entries_in_view[display_df.loc[entries_in_view.index, "position"] == -1]
        else:
            long_entries = entries_in_view
            short_entries = pd.DataFrame()

        close_col = col_map["close"]

        if not long_entries.empty:
            fig.add_trace(
                go.Scatter(
                    x=long_entries.index, y=long_entries[close_col],
                    mode="markers+text", name="做多進場",
                    marker=dict(symbol="triangle-up", size=11, color=p["green"],
                                line=dict(color="white", width=1.5)),
                    text="L", textposition="top center",
                    textfont=dict(color="white", size=9),
                ),
                row=1, col=1,
            )

        if not short_entries.empty:
            fig.add_trace(
                go.Scatter(
                    x=short_entries.index, y=short_entries[close_col],
                    mode="markers+text", name="做空進場",
                    marker=dict(symbol="triangle-down", size=11, color=p["red"],
                                line=dict(color="white", width=1.5)),
                    text="S", textposition="bottom center",
                    textfont=dict(color="white", size=9),
                ),
                row=1, col=1,
            )

    exits_in_view = display_df[display_df["exit"]] if "exit" in display_df.columns else pd.DataFrame()
    if not exits_in_view.empty:
        close_col = col_map["close"]
        fig.add_trace(
            go.Scatter(
                x=exits_in_view.index, y=exits_in_view[close_col],
                mode="markers+text", name="出場",
                marker=dict(symbol="x", size=9, color=p["orange"],
                            line=dict(color="white", width=1)),
                text="X", textposition="top center",
                textfont=dict(color=p["orange"], size=9),
            ),
            row=1, col=1,
        )

    if col_map.get("volume"):
        open_col = col_map["open"]
        close_col = col_map["close"]
        vol_col = col_map["volume"]
        colors = [p["red"] if display_df[close_col].iloc[i] < display_df[open_col].iloc[i]
                  else p["green_light"] for i in range(len(display_df))]
        fig.add_trace(
            go.Bar(
                x=display_df.index, y=display_df[vol_col],
                name="成交量",
                marker_color=colors,
                opacity=0.6,
            ),
            row=2, col=1,
        )
    else:
        fig.add_annotation(
            text="（配對交易：無成交量資料）",
            xref="paper", yref="paper",
            x=0.5, y=0.15,
            showarrow=False,
            font=dict(color=p["text_muted"], size=12),
        )

    # === v2: 高亮選中交易（垂直虛線 + 標註框）===
    if selected_idx is not None and 0 <= selected_idx < len(trades):
        sel_trade = trades[selected_idx]
        entry_time = sel_trade.get("entry_time")
        exit_time = sel_trade.get("exit_time")
        pnl = sel_trade.get("pnl", 0)
        pnl_pct = sel_trade.get("pnl_pct", 0) * 100
        entry_price = sel_trade.get("entry_price", 0)
        exit_price = sel_trade.get("exit_price", 0)
        is_profit = pnl >= 0
        vline_color = p["green"] if is_profit else p["red"]

        # 進場-出場間填色（v3：layer="below" 讓 hover 穿透）
        if entry_time is not None and exit_time is not None:
            try:
                entry_ts = pd.Timestamp(entry_time)
                exit_ts = pd.Timestamp(exit_time)
                # 找出區間內所有 K 線
                in_range = display_df[(display_df.index >= entry_ts) & (display_df.index <= exit_ts)]
                if not in_range.empty:
                    fill_color = f"rgba(34, 197, 94, 0.10)" if is_profit else "rgba(239, 68, 68, 0.10)"
                    fig.add_vrect(
                        x0=entry_ts, x1=exit_ts,
                        fillcolor=fill_color,
                        opacity=0.6,
                        layer="below",  # v3: 在資料下方，hover 穿透
                        line_width=0,
                        row=1, col=1,
                    )
            except Exception:
                pass

        # 進場垂直虛線（v3：layer="below"）
        if entry_time is not None and pd.notna(entry_time):
            entry_ts = pd.Timestamp(entry_time)
            if entry_ts in display_df.index or entry_ts in result_df.index:
                fig.add_vline(
                    x=entry_ts,
                    line=dict(color=vline_color, width=2.5, dash="dot"),
                    opacity=0.85,
                    layer="below",  # v3: 讓 hover 穿透
                    row=1, col=1,
                )
                # 標註框（進場）
                fig.add_annotation(
                    x=entry_ts,
                    y=1.04,
                    yref="paper",
                    text=f"<b>L</b><br>${entry_price:,.2f}",
                    showarrow=False,
                    font=dict(color=vline_color, size=10, family=p["font_mono"]),
                    bgcolor=p["bg_card"],
                    bordercolor=vline_color,
                    borderwidth=1,
                    borderpad=3,
                    xanchor="left",
                    yanchor="bottom",
                )

        # 出場垂直虛線（v3：layer="below"）
        if exit_time is not None and pd.notna(exit_time):
            exit_ts = pd.Timestamp(exit_time)
            if exit_ts in display_df.index or exit_ts in result_df.index:
                fig.add_vline(
                    x=exit_ts,
                    line=dict(color=p["orange"], width=2.5, dash="dot"),
                    opacity=0.85,
                    layer="below",  # v3: 讓 hover 穿透
                    row=1, col=1,
                )
                # 標註框（出場）
                fig.add_annotation(
                    x=exit_ts,
                    y=1.04,
                    yref="paper",
                    text=f"<b>X</b><br>${exit_price:,.2f}",
                    showarrow=False,
                    font=dict(color=p["orange"], size=10, family=p["font_mono"]),
                    bgcolor=p["bg_card"],
                    bordercolor=p["orange"],
                    borderwidth=1,
                    borderpad=3,
                    xanchor="right",
                    yanchor="bottom",
                )

        # 底部狀態列（PnL 摘要）
        fig.add_annotation(
            x=0.5, y=-0.18,
            xref="paper", yref="paper",
            text=f"<b>#{selected_idx + 1}</b> · {pnl_pct:+.2f}% · ${pnl:+,.2f}",
            showarrow=False,
            font=dict(color=vline_color, size=13, family=p["font_mono"]),
            xanchor="center",
        )

    fig.update_layout(
        height=620,
        template=get_current_theme()["plotly_template"],
        paper_bgcolor=p["bg"],
        plot_bgcolor=p["bg"],
        font=dict(color=p["text_primary"], family="system-ui", size=12),
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=12),
        ),
        margin=dict(l=60, r=24, t=24, b=40),
        xaxis=dict(gridcolor=p["border"], showgrid=True, zeroline=False),
        xaxis2=dict(gridcolor=p["border"], showgrid=False, zeroline=False),
        yaxis=dict(
            gridcolor=p["border"], showgrid=True, zeroline=False,
            side="left",
        ),
        yaxis2=dict(
            gridcolor=p["border"], showgrid=True, zeroline=False,
            side="left",
        ),
    )

    st.plotly_chart(fig, use_container_width=True)


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
    text-transform: uppercase;
    letter-spacing: 0.08em;
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
        st.warning("⚠️ 交易數不足（需要至少 5 筆交易才能進行有意義的蒙地卡羅模擬）")
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
            st.error(f"❌ {mc['error']}")
            return

        p_stats = mc["percentiles"]

        st.markdown(f"""
<div style="
    color: {p['text_secondary']};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
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
                help="平均報酬 / 平均回撤",
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
        st.plotly_chart(fig, use_container_width=True)

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
            st.plotly_chart(fig_ret, use_container_width=True)

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
            st.plotly_chart(fig_dd, use_container_width=True)

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
