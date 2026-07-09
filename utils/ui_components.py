"""
TradingView 風格的回測結果 UI 元件
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Dict, List, Any


# === TradingView 風格配色 ===
TV_COLORS = {
    "bg_dark": "#131722",
    "bg_panel": "#1c2030",
    "bg_card": "#1e222d",
    "border": "#2a2e39",
    "text_primary": "#d1d4dc",
    "text_secondary": "#787b86",
    "text_muted": "#5d606b",
    "green": "#26a69a",       # TradingView 的獲利綠
    "green_light": "#4caf50",
    "red": "#ef5350",         # TradingView 的虧損紅
    "red_light": "#e57373",
    "blue": "#2962ff",
    "orange": "#ff9800",
    "purple": "#ab47bc",
    "yellow": "#ffd600",
}


def calc_calmar_ratio(total_return_pct: float, max_drawdown_pct: float) -> float:
    """Calmar Ratio = 年化報酬 / 最大回撤"""
    if max_drawdown_pct == 0:
        return 0
    return total_return_pct / abs(max_drawdown_pct)


def calc_sortino_ratio(returns: pd.Series, risk_free: float = 0) -> float:
    """Sortino Ratio = 報酬 / 下行波動率"""
    downside = returns[returns < 0]
    if len(downside) == 0 or downside.std() == 0:
        return 0
    excess = returns - risk_free
    return (excess.mean() / downside.std()) * np.sqrt(252)


def calc_recovery_factor(total_return_pct: float, max_drawdown_pct: float) -> float:
    """Recovery Factor = 總報酬 / 最大回撤絕對值"""
    if max_drawdown_pct == 0:
        return 0
    return total_return_pct / abs(max_drawdown_pct)


def calc_avg_win_loss_ratio(avg_win: float, avg_loss: float) -> float:
    """風報比 = 平均獲利 / 平均虧損絕對值"""
    if avg_loss == 0:
        return 0
    return abs(avg_win / avg_loss)


def calc_expectancy(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """期望值 = 勝率*平均獲利 - (1-勝率)*|平均虧損|"""
    return (win_rate / 100) * avg_win - (1 - win_rate / 100) * abs(avg_loss)


def render_overview(metrics: Dict, result_df: pd.DataFrame, initial_capital: float) -> None:
    """
    TradingView 風格的 Overview 分頁
    - 頂部大型淨利潤數字
    - 權益曲線 + Drawdown
    - 6 個關鍵指標
    - 勝率甜甜圈圖
    """
    # 計算額外指標
    total_return = metrics.get("total_return_pct", 0)
    final_equity = metrics.get("final_equity", initial_capital)
    net_profit = final_equity - initial_capital
    max_dd = metrics.get("max_drawdown_pct", 0)
    win_rate = metrics.get("win_rate", 0)
    n_trades = metrics.get("n_trades", 0)
    avg_win = metrics.get("avg_win_pct", 0)
    avg_loss = metrics.get("avg_loss_pct", 0)
    sharpe = metrics.get("sharpe_ratio", 0)
    profit_factor = metrics.get("profit_factor", 0)
    buy_hold = metrics.get("buy_hold_return_pct", 0)

    returns = result_df["strategy_returns"].dropna()
    sortino = calc_sortino_ratio(returns)
    calmar = calc_calmar_ratio(total_return, max_dd)
    recovery = calc_recovery_factor(total_return, max_dd)
    rr_ratio = calc_avg_win_loss_ratio(avg_win, avg_loss)
    expectancy = calc_expectancy(win_rate, avg_win, avg_loss)

    # === 頂部：大型淨利潤數字（TradingView 風格） ===
    profit_color = TV_COLORS["green"] if net_profit >= 0 else TV_COLORS["red"]
    profit_pct_color = TV_COLORS["green"] if total_return >= 0 else TV_COLORS["red"]
    delta_color = TV_COLORS["green"] if total_return >= buy_hold else TV_COLORS["red"]

    st.markdown(f"""
    <div style="background: {TV_COLORS['bg_card']}; padding: 24px; border-radius: 8px; margin-bottom: 20px; border: 1px solid {TV_COLORS['border']};">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;">
            <div>
                <div style="color: {TV_COLORS['text_secondary']}; font-size: 14px; margin-bottom: 4px;">淨利潤 (NET PROFIT)</div>
                <div style="color: {profit_color}; font-size: 48px; font-weight: 700; line-height: 1.1;">
                    ${net_profit:+,.2f}
                </div>
            </div>
            <div style="text-align: right;">
                <div style="color: {TV_COLORS['text_secondary']}; font-size: 14px; margin-bottom: 4px;">總報酬率 (RETURN)</div>
                <div style="color: {profit_pct_color}; font-size: 36px; font-weight: 700;">
                    {total_return:+.2f}%
                </div>
                <div style="color: {delta_color}; font-size: 14px; margin-top: 4px;">
                    vs 買進持有 {total_return - buy_hold:+.2f}%
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # === 中段：權益曲線 + Drawdown ===
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.72, 0.28],
        subplot_titles=("權益曲線 (Equity Curve)", "回撤 (Drawdown)")
    )

    # 權益曲線 - 綠色或紅色根據整體表現
    equity_color = TV_COLORS["green"] if net_profit >= 0 else TV_COLORS["red"]
    fig.add_trace(
        go.Scatter(
            x=result_df.index, y=result_df["equity"],
            name="策略權益",
            line=dict(color=equity_color, width=2.5),
            fill="tozeroy",
            fillcolor=f"rgba{(38, 166, 154, 0.1) if net_profit >= 0 else (239, 83, 80, 0.1)}",
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=result_df.index, y=result_df["buy_hold"],
            name="買進持有",
            line=dict(color=TV_COLORS["orange"], width=1.5, dash="dash"),
        ),
        row=1, col=1
    )

    # Drawdown
    cummax = result_df["equity"].cummax()
    drawdown = (result_df["equity"] - cummax) / cummax * 100
    fig.add_trace(
        go.Scatter(
            x=result_df.index, y=drawdown,
            name="回撤 %",
            fill="tozeroy",
            line=dict(color=TV_COLORS["red"], width=1),
            fillcolor="rgba(239, 83, 80, 0.3)",
        ),
        row=2, col=1
    )

    fig.update_layout(
        height=500,
        hovermode="x unified",
        template="plotly_dark",
        paper_bgcolor=TV_COLORS["bg_dark"],
        plot_bgcolor=TV_COLORS["bg_dark"],
        font=dict(color=TV_COLORS["text_primary"]),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            bgcolor="rgba(0,0,0,0)"
        ),
        margin=dict(l=60, r=20, t=60, b=40),
    )
    fig.update_xaxes(gridcolor=TV_COLORS["border"], showgrid=True)
    fig.update_yaxes(gridcolor=TV_COLORS["border"], showgrid=True)
    fig.update_yaxes(title_text="USDT", row=1, col=1)
    fig.update_yaxes(title_text="%", row=2, col=1)

    st.plotly_chart(fig, use_container_width=True)

    # === 6 個關鍵指標網格（TradingView 風格） ===
    st.markdown(f"""
    <div style="color: {TV_COLORS['text_secondary']}; font-size: 13px; margin: 16px 0 8px 0; text-transform: uppercase; letter-spacing: 0.5px;">
        ⚡ 關鍵指標 (Key Metrics)
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("總交易數", f"{n_trades}")
    with col2:
        wr_color = TV_COLORS["green"] if win_rate >= 50 else TV_COLORS["red"]
        st.metric("勝率", f"{win_rate:.1f}%")
    with col3:
        st.metric("利潤因子", f"{profit_factor:.2f}" if profit_factor != np.inf else "∞")
    with col4:
        st.metric("最大回撤", f"{max_dd:.2f}%")
    with col5:
        st.metric("Sharpe", f"{sharpe:.2f}")
    with col6:
        st.metric("風報比", f"{rr_ratio:.2f}")

    # === 第二行：進階指標 ===
    col7, col8, col9, col10, col11, col12 = st.columns(6)
    with col7:
        st.metric("Sortino", f"{sortino:.2f}")
    with col8:
        st.metric("Calmar", f"{calmar:.2f}")
    with col9:
        st.metric("Recovery", f"{recovery:.2f}")
    with col10:
        st.metric("期望值", f"{expectancy:+.2f}%")
    with col11:
        st.metric("最終權益", f"${final_equity:,.0f}")
    with col12:
        st.metric("買進持有", f"{buy_hold:+.2f}%")


def render_performance_summary(trades: List[Dict], metrics: Dict) -> None:
    """
    TradingView 風格的 Performance Summary 分頁
    - 分區塊：All / Long / Short
    - 每組詳細指標表格
    """
    if not trades:
        st.info("無交易記錄")
        return

    trades_df = pd.DataFrame(trades)

    # 分區塊計算
    blocks = {
        "📊 所有交易 (All Trades)": trades_df,
        "🟢 做多 (Long Trades)": trades_df[trades_df["direction"] == "long"] if "direction" in trades_df.columns else pd.DataFrame(),
        "🔴 做空 (Short Trades)": trades_df[trades_df["direction"] == "short"] if "direction" in trades_df.columns else pd.DataFrame(),
    }

    for title, df_block in blocks.items():
        if df_block.empty:
            continue

        st.markdown(f"""
        <div style="color: {TV_COLORS['text_primary']}; font-size: 18px; font-weight: 600; margin: 20px 0 12px 0; padding: 8px 12px; background: {TV_COLORS['bg_card']}; border-left: 3px solid {TV_COLORS['blue']};">
            {title}
        </div>
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

        # 兩欄指標
        col_a, col_b, col_c, col_d = st.columns(4)

        with col_a:
            st.markdown(_metric_card("總交易數", f"{n}", "neutral"), unsafe_allow_html=True)
            st.markdown(_metric_card("獲利交易", f"{len(winners)}", "positive" if len(winners) > 0 else "neutral"), unsafe_allow_html=True)
            st.markdown(_metric_card("虧損交易", f"{len(losers)}", "negative" if len(losers) > 0 else "neutral"), unsafe_allow_html=True)
            st.markdown(_metric_card("勝率", f"{win_rate:.1f}%", "positive" if win_rate >= 50 else "negative"), unsafe_allow_html=True)

        with col_b:
            st.markdown(_metric_card("淨利潤", f"${net_profit:+,.2f}", "positive" if net_profit > 0 else "negative"), unsafe_allow_html=True)
            st.markdown(_metric_card("毛利", f"${gross_profit:,.2f}", "positive"), unsafe_allow_html=True)
            st.markdown(_metric_card("毛損", f"${gross_loss:,.2f}", "negative"), unsafe_allow_html=True)
            st.markdown(_metric_card("利潤因子", f"{gross_profit/gross_loss:.2f}" if gross_loss > 0 else "∞", "positive" if gross_profit > gross_loss else "negative"), unsafe_allow_html=True)

        with col_c:
            st.markdown(_metric_card("平均獲利", f"{avg_win:+.2f}%", "positive"), unsafe_allow_html=True)
            st.markdown(_metric_card("平均虧損", f"{avg_loss:+.2f}%", "negative"), unsafe_allow_html=True)
            st.markdown(_metric_card("最大單筆獲利", f"{largest_win:+.2f}%", "positive"), unsafe_allow_html=True)
            st.markdown(_metric_card("最大單筆虧損", f"{largest_loss:+.2f}%", "negative"), unsafe_allow_html=True)

        with col_d:
            st.markdown(_metric_card("風報比", f"{abs(avg_win/avg_loss):.2f}" if avg_loss != 0 else "∞", "positive" if abs(avg_win) > abs(avg_loss) else "negative"), unsafe_allow_html=True)
            st.markdown(_metric_card("平均持倉 (h)", f"{avg_duration:.1f}", "neutral"), unsafe_allow_html=True)
            st.markdown(_metric_card("最大連勝", f"{max_consec_wins}", "positive"), unsafe_allow_html=True)
            st.markdown(_metric_card("最大連敗", f"{max_consec_losses}", "negative"), unsafe_allow_html=True)


def render_list_of_trades(trades: List[Dict]) -> None:
    """TradingView 風格的交易清單"""
    if not trades:
        st.info("無交易記錄")
        return

    trades_df = pd.DataFrame(trades)

    # 格式化時間
    if "entry_time" in trades_df.columns:
        trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"]).dt.tz_localize(None)
    if "exit_time" in trades_df.columns:
        trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"]).dt.tz_localize(None)

    # 加上買進持有累計盈餘
    trades_df["累計 PnL"] = trades_df["pnl"].cumsum().round(2)

    # 格式化欄位
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

    # 重新命名
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

    # 顯示
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

    # 下載按鈕
    from datetime import datetime
    csv = trades_df_display.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 下載交易明細 CSV",
        data=csv,
        file_name=f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )


def render_charts(result_df: pd.DataFrame, trades: List[Dict]) -> None:
    """TradingView 風格的圖表區"""
    st.subheader("📈 價格走勢 + 進出場標記")

    # 顯示最近 N 根 K 線
    display_n = st.slider("顯示最近 N 根 K 線", min_value=50, max_value=min(1000, len(result_df)), value=min(200, len(result_df)), step=50)
    display_df = result_df.tail(display_n).copy()

    # 圖表
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.75, 0.25],
        subplot_titles=(f"價格走勢 (最近 {display_n} 根)", "成交量")
    )

    # K 線
    fig.add_trace(
        go.Candlestick(
            x=display_df.index,
            open=display_df["open"],
            high=display_df["high"],
            low=display_df["low"],
            close=display_df["close"],
            name="K 線",
            increasing_line_color=TV_COLORS["green"],
            decreasing_line_color=TV_COLORS["red"],
        ),
        row=1, col=1
    )

    # 進場標記
    entries_in_view = display_df[display_df["entry"]]
    if not entries_in_view.empty:
        # 區分多空
        if "position" in display_df.columns:
            long_entries = entries_in_view[display_df.loc[entries_in_view.index, "position"] == 1]
            short_entries = entries_in_view[display_df.loc[entries_in_view.index, "position"] == -1]
        else:
            long_entries = entries_in_view
            short_entries = pd.DataFrame()

        if not long_entries.empty:
            fig.add_trace(
                go.Scatter(
                    x=long_entries.index, y=long_entries["close"],
                    mode="markers+text", name="做多進場",
                    marker=dict(symbol="triangle-up", size=14, color=TV_COLORS["green"],
                                line=dict(color="white", width=1.5)),
                    text="L", textposition="top center",
                    textfont=dict(color="white", size=10),
                ),
                row=1, col=1
            )

        if not short_entries.empty:
            fig.add_trace(
                go.Scatter(
                    x=short_entries.index, y=short_entries["close"],
                    mode="markers+text", name="做空進場",
                    marker=dict(symbol="triangle-down", size=14, color=TV_COLORS["red"],
                                line=dict(color="white", width=1.5)),
                    text="S", textposition="bottom center",
                    textfont=dict(color="white", size=10),
                ),
                row=1, col=1
            )

    # 出場標記
    exits_in_view = display_df[display_df["exit"]]
    if not exits_in_view.empty:
        fig.add_trace(
            go.Scatter(
                x=exits_in_view.index, y=exits_in_view["close"],
                mode="markers+text", name="出場",
                marker=dict(symbol="x", size=10, color=TV_COLORS["yellow"],
                            line=dict(color="white", width=1)),
                text="X", textposition="top center",
                textfont=dict(color=TV_COLORS["yellow"], size=10),
            ),
            row=1, col=1
        )

    # 成交量
    colors = [TV_COLORS["red"] if display_df["close"].iloc[i] < display_df["open"].iloc[i]
              else TV_COLORS["green"] for i in range(len(display_df))]
    fig.add_trace(
        go.Bar(
            x=display_df.index, y=display_df["volume"],
            name="成交量",
            marker_color=colors,
            opacity=0.7,
        ),
        row=2, col=1
    )

    fig.update_layout(
        height=700,
        template="plotly_dark",
        paper_bgcolor=TV_COLORS["bg_dark"],
        plot_bgcolor=TV_COLORS["bg_dark"],
        font=dict(color=TV_COLORS["text_primary"]),
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
        ),
        margin=dict(l=60, r=20, t=60, b=40),
    )
    fig.update_xaxes(gridcolor=TV_COLORS["border"], showgrid=True)
    fig.update_yaxes(gridcolor=TV_COLORS["border"], showgrid=True)
    st.plotly_chart(fig, use_container_width=True)


# === 內部輔助函式 ===

def _metric_card(label: str, value: str, sentiment: str = "neutral") -> str:
    """渲染 TradingView 風格的指標卡片"""
    if sentiment == "positive":
        color = TV_COLORS["green"]
    elif sentiment == "negative":
        color = TV_COLORS["red"]
    else:
        color = TV_COLORS["text_primary"]

    return f"""
    <div style="background: {TV_COLORS['bg_card']}; padding: 10px 14px; margin: 4px 0; border-radius: 4px; border-left: 3px solid {color}; display: flex; justify-content: space-between; align-items: center;">
        <div style="color: {TV_COLORS['text_secondary']}; font-size: 12px;">{label}</div>
        <div style="color: {color}; font-size: 14px; font-weight: 600;">{value}</div>
    </div>
    """


def _max_consecutive(series: pd.Series) -> int:
    """計算最大連續 True 數量"""
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
