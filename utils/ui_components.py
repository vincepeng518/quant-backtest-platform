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


# === Overview 頁：KPI 卡片 + 主圖 + 交易統計 ===
def render_overview(metrics: Dict, result_df: pd.DataFrame, initial_capital: float) -> None:
    """TradingView 風格 Overview。"""
    p = _palette()

    # 區段標題
    st.markdown(f"""
<div style="
    color: {p['text_secondary']};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
    margin-bottom: 8px;
    margin-top: 4px;
">關鍵指標</div>
""", unsafe_allow_html=True)

    # 修正：將 initial_capital 補進 metrics（render_kpi_cards 用）
    metrics_with_cap = {**metrics, "initial_capital": initial_capital}
    render_kpi_cards(metrics_with_cap, result_df)

    # 區段間距
    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

    # 主圖區段
    st.markdown(f"""
<div style="
    color: {p['text_secondary']};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
    margin-bottom: 8px;
">權益曲線</div>
""", unsafe_allow_html=True)

    metrics_with_cap = {**metrics, "initial_capital": initial_capital}
    render_equity_chart(result_df, metrics_with_cap)


def render_performance_summary(trades: List[Dict], metrics: Dict) -> None:
    """Performance Summary 頁：交易統計網格 + 月報酬熱圖。"""
    p = _palette()

    if not trades:
        st.info("無交易記錄")
        return

    trades_df = pd.DataFrame(trades)

    # 多維度分組
    blocks = [
        ("📊 全部交易", trades_df),
        ("🟢 做多", trades_df[trades_df["direction"] == "long"] if "direction" in trades_df.columns else pd.DataFrame()),
        ("🔴 做空", trades_df[trades_df["direction"] == "short"] if "direction" in trades_df.columns else pd.DataFrame()),
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
    """List of Trades 頁：交易明細表。"""
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

    st.dataframe(
        trades_df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "進場時間": st.column_config.DatetimeColumn("進場時間", format="YYYY-MM-DD HH:mm"),
            "出場時間": st.column_config.DatetimeColumn("出場時間", format="YYYY-MM-DD HH:mm"),
            "進場價": st.column_config.NumberColumn("進場價", format="$%.2f"),
            "出場價": st.column_config.NumberColumn("出場價", format="$%.2f"),
            "報酬 %": st.column_config.NumberColumn("報酬 %", format="%+.2f%%"),
            "損益 (USDT)": st.column_config.NumberColumn("損益 (USDT)", format="$%+.2f"),
            "累計 PnL": st.column_config.NumberColumn("累計 PnL", format="$%+.2f"),
            "持倉 (h)": st.column_config.NumberColumn("持倉 (h)", format="%.1f"),
        },
        height=500,
    )

    from datetime import datetime
    csv = trades_df_display.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 下載交易明細 CSV",
        data=csv,
        file_name=f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )


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
    """價格走勢圖（TradingView 風格 K 線 + Volume）。"""
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
">價格走勢 + 進出場標記</div>
""", unsafe_allow_html=True)

    col_map = _resolve_chart_columns(result_df)
    if not col_map:
        st.error("❌ 找不到價格欄位（open/high/low/close）")
        st.info("請確認您的回測資料有正確的 OHLC 欄位")
        return

    display_n = st.slider("顯示最近 N 根 K 線", min_value=50, max_value=min(1000, len(result_df)),
                            value=min(200, len(result_df)), step=50)
    display_df = result_df.tail(display_n).copy()

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

    if st.button("🎲 執行蒙地卡羅模擬", type="primary", use_container_width=True):
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
">📈 權益曲線分布（隨機路徑）</div>
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
">📊 最終報酬率 &amp; 最大回撤分布</div>
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
">📋 風險評估總結</div>
""", unsafe_allow_html=True)

        if mc["ruin_prob"] > 20:
            risk_level = "🔴 高風險"
            risk_msg = "破產機率過高（>20%），強烈建議重新設計策略或降低倉位。"
        elif mc["ruin_prob"] > 10:
            risk_level = "🟠 中風險"
            risk_msg = "存在一定風險，建議謹慎使用，考慮加入倉位管理。"
        elif p_stats["dd_p95"] > 40:
            risk_level = "🟡 需注意"
            risk_msg = "破產機率低，但最壞情況回撤可能較大，請做好風險控制。"
        elif p_stats["return_p5"] > 0:
            risk_level = "🟢 低風險"
            risk_msg = "在 95% 信心區間下仍然獲利，策略非常穩健。"
        else:
            risk_level = "🟡 觀察中"
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
