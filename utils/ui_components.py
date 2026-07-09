"""
Notion 風格的回測結果 UI 元件
- 淺色背景 (#FFFFFF)
- 簡潔排版、寬鬆留白
- 細邊框、極簡陰影
- 顏色編碼：綠色(獲利)/ 紅色(虧損)/ 藍色(強調)
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Dict, List, Any


# === Notion 風格配色（淺色主題） ===
N_COLORS = {
    "bg": "#FFFFFF",
    "bg_subtle": "#F9FAFB",
    "bg_card": "#FFFFFF",
    "border": "#E5E7EB",
    "border_strong": "#D1D5DB",
    "text_primary": "#1F2937",
    "text_secondary": "#6B7280",
    "text_muted": "#9CA3AF",
    "green": "#10B981",       # 獲利
    "green_light": "#D1FAE5",
    "green_text": "#047857",
    "red": "#EF4444",         # 虧損
    "red_light": "#FEE2E2",
    "red_text": "#B91C1C",
    "blue": "#2563EB",        # 強調
    "blue_light": "#DBEAFE",
    "orange": "#F59E0B",
    "purple": "#8B5CF6",
    "yellow": "#EAB308",
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
    """Notion 風格的 Overview 分頁"""
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

    # 頂部：大型淨利潤（Notion 風格）
    profit_color = N_COLORS["green_text"] if net_profit >= 0 else N_COLORS["red_text"]
    profit_pct_color = N_COLORS["green_text"] if total_return >= 0 else N_COLORS["red_text"]
    delta_color = N_COLORS["green_text"] if total_return >= buy_hold else N_COLORS["red_text"]

    st.markdown(f"""
    <div style="background: {N_COLORS['bg_subtle']}; padding: 28px 32px; border-radius: 8px; margin-bottom: 24px; border: 1px solid {N_COLORS['border']};">
        <div style="display: flex; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; gap: 16px;">
            <div>
                <div style="color: {N_COLORS['text_secondary']}; font-size: 13px; margin-bottom: 6px; font-weight: 500;">淨利潤</div>
                <div style="color: {profit_color}; font-size: 40px; font-weight: 700; line-height: 1.1; letter-spacing: -0.02em;">
                    ${net_profit:+,.2f}
                </div>
            </div>
            <div style="text-align: right;">
                <div style="color: {N_COLORS['text_secondary']}; font-size: 13px; margin-bottom: 6px; font-weight: 500;">總報酬率</div>
                <div style="color: {profit_pct_color}; font-size: 28px; font-weight: 700; line-height: 1.1;">
                    {total_return:+.2f}%
                </div>
                <div style="color: {delta_color}; font-size: 12px; margin-top: 6px; font-weight: 500;">
                    vs 買進持有 {total_return - buy_hold:+.2f}%
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 中段：權益曲線 + Drawdown（淺色風格）
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.72, 0.28],
        subplot_titles=("權益曲線", "回撤")
    )

    equity_color = N_COLORS["green"] if net_profit >= 0 else N_COLORS["red"]
    fillcolor_rgba = "rgba(16, 185, 129, 0.08)" if net_profit >= 0 else "rgba(239, 68, 68, 0.08)"

    fig.add_trace(
        go.Scatter(
            x=result_df.index, y=result_df["equity"],
            name="策略權益",
            line=dict(color=equity_color, width=2),
            fill="tozeroy",
            fillcolor=fillcolor_rgba,
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=result_df.index, y=result_df["buy_hold"],
            name="買進持有",
            line=dict(color=N_COLORS["orange"], width=1.5, dash="dash"),
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
            line=dict(color=N_COLORS["red"], width=1),
            fillcolor="rgba(239, 68, 68, 0.15)",
        ),
        row=2, col=1
    )

    fig.update_layout(
        height=450,
        hovermode="x unified",
        template="plotly_white",
        paper_bgcolor=N_COLORS["bg"],
        plot_bgcolor=N_COLORS["bg"],
        font=dict(color=N_COLORS["text_primary"], family="system-ui"),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=50, r=20, t=50, b=30),
    )
    fig.update_xaxes(gridcolor=N_COLORS["border"], showgrid=True, zeroline=False)
    fig.update_yaxes(gridcolor=N_COLORS["border"], showgrid=True, zeroline=False)
    fig.update_yaxes(title_text="USDT", row=1, col=1)
    fig.update_yaxes(title_text="%", row=2, col=1)

    st.plotly_chart(fig, use_container_width=True)

    # 關鍵指標（Notion 風格：簡潔的網格）
    st.markdown(f"""
    <div style="color: {N_COLORS['text_secondary']}; font-size: 11px; margin: 20px 0 8px 0; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600;">
        關鍵指標
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("總交易數", f"{n_trades}")
        st.metric("勝率", f"{win_rate:.1f}%")
    with col2:
        st.metric("利潤因子", f"{profit_factor:.2f}" if profit_factor != np.inf else "∞")
        st.metric("最大回撤", f"{max_dd:.2f}%")
    with col3:
        st.metric("Sharpe", f"{sharpe:.2f}")
        st.metric("Sortino", f"{sortino:.2f}")
    with col4:
        st.metric("風報比", f"{rr_ratio:.2f}")
        st.metric("Calmar", f"{calmar:.2f}")

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.metric("Recovery", f"{recovery:.2f}")
    with col6:
        st.metric("期望值", f"{expectancy:+.2f}%")
    with col7:
        st.metric("最終權益", f"${final_equity:,.0f}")
    with col8:
        st.metric("買進持有", f"{buy_hold:+.2f}%")


def render_performance_summary(trades: List[Dict], metrics: Dict) -> None:
    """Notion 風格的 Performance Summary"""
    if not trades:
        st.info("無交易記錄")
        return

    trades_df = pd.DataFrame(trades)

    blocks = {
        "📊 所有交易": trades_df,
        "🟢 做多": trades_df[trades_df["direction"] == "long"] if "direction" in trades_df.columns else pd.DataFrame(),
        "🔴 做空": trades_df[trades_df["direction"] == "short"] if "direction" in trades_df.columns else pd.DataFrame(),
    }

    for title, df_block in blocks.items():
        if df_block.empty:
            continue

        st.markdown(f"""
        <div style="font-size: 1rem; font-weight: 600; color: {N_COLORS['text_primary']}; margin: 24px 0 12px 0; padding-bottom: 8px; border-bottom: 2px solid {N_COLORS['border']};">
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
    """Notion 風格的交易清單"""
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
    """
    自動偵測並解析圖表需要的欄位
    - 支援單標的：open/high/low/close/volume
    - 支援配對交易：BTC/USDT_open、ETH/USDT_open 等
    """
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
    """Notion 風格的圖表區"""
    st.markdown("### 📈 價格走勢 + 進出場標記")

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
        vertical_spacing=0.06,
        row_heights=[0.75, 0.25],
        subplot_titles=(f"價格走勢 (最近 {display_n} 根)", "成交量")
    )

    candlestick_kwargs = {
        "x": display_df.index,
        "open": display_df[col_map["open"]],
        "high": display_df[col_map["high"]],
        "low": display_df[col_map["low"]],
        "close": display_df[col_map["close"]],
        "increasing_line_color": N_COLORS["green"],
        "decreasing_line_color": N_COLORS["red"],
        "name": col_map.get("symbol", "K 線"),
    }
    fig.add_trace(go.Candlestick(**candlestick_kwargs), row=1, col=1)

    if col_map.get("mode") == "pair" and "close2" in col_map:
        fig.add_trace(
            go.Scatter(
                x=display_df.index, y=display_df[col_map["close2"]],
                name=f"{col_map['symbol2']} 價格",
                line=dict(color=N_COLORS["orange"], width=1.5, dash="dot"),
                opacity=0.6,
            ),
            row=1, col=1
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
                    marker=dict(symbol="triangle-up", size=12, color=N_COLORS["green"],
                                line=dict(color="white", width=1.5)),
                    text="L", textposition="top center",
                    textfont=dict(color="white", size=9),
                ),
                row=1, col=1
            )

        if not short_entries.empty:
            fig.add_trace(
                go.Scatter(
                    x=short_entries.index, y=short_entries[close_col],
                    mode="markers+text", name="做空進場",
                    marker=dict(symbol="triangle-down", size=12, color=N_COLORS["red"],
                                line=dict(color="white", width=1.5)),
                    text="S", textposition="bottom center",
                    textfont=dict(color="white", size=9),
                ),
                row=1, col=1
            )

    exits_in_view = display_df[display_df["exit"]] if "exit" in display_df.columns else pd.DataFrame()
    if not exits_in_view.empty:
        close_col = col_map["close"]
        fig.add_trace(
            go.Scatter(
                x=exits_in_view.index, y=exits_in_view[close_col],
                mode="markers+text", name="出場",
                marker=dict(symbol="x", size=9, color=N_COLORS["orange"],
                            line=dict(color="white", width=1)),
                text="X", textposition="top center",
                textfont=dict(color=N_COLORS["orange"], size=9),
            ),
            row=1, col=1
        )

    if col_map.get("volume"):
        open_col = col_map["open"]
        close_col = col_map["close"]
        vol_col = col_map["volume"]
        colors = [N_COLORS["red"] if display_df[close_col].iloc[i] < display_df[open_col].iloc[i]
                  else N_COLORS["green_light"] for i in range(len(display_df))]
        fig.add_trace(
            go.Bar(
                x=display_df.index, y=display_df[vol_col],
                name="成交量",
                marker_color=colors,
                opacity=0.6,
            ),
            row=2, col=1
        )
    else:
        fig.add_annotation(
            text="（配對交易：無成交量資料）",
            xref="paper", yref="paper",
            x=0.5, y=0.15,
            showarrow=False,
            font=dict(color=N_COLORS["text_muted"], size=12),
        )

    fig.update_layout(
        height=650,
        template="plotly_white",
        paper_bgcolor=N_COLORS["bg"],
        plot_bgcolor=N_COLORS["bg"],
        font=dict(color=N_COLORS["text_primary"], family="system-ui"),
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=50, r=20, t=50, b=30),
    )
    fig.update_xaxes(gridcolor=N_COLORS["border"], showgrid=True, zeroline=False)
    fig.update_yaxes(gridcolor=N_COLORS["border"], showgrid=True, zeroline=False)
    st.plotly_chart(fig, use_container_width=True)


def _metric_card(label: str, value: str, sentiment: str = "neutral") -> str:
    """Notion 風格的指標卡片（簡潔、淺色）"""
    if sentiment == "positive":
        color = N_COLORS["green_text"]
        bg = N_COLORS["green_light"]
    elif sentiment == "negative":
        color = N_COLORS["red_text"]
        bg = N_COLORS["red_light"]
    else:
        color = N_COLORS["text_primary"]
        bg = N_COLORS["bg_subtle"]

    return f"""
    <div style="background: {N_COLORS['bg']}; padding: 10px 14px; margin: 4px 0; border-radius: 6px; border: 1px solid {N_COLORS['border']}; display: flex; justify-content: space-between; align-items: center;">
        <div style="color: {N_COLORS['text_secondary']}; font-size: 12px;">{label}</div>
        <div style="background: {bg}; color: {color}; padding: 2px 8px; border-radius: 4px; font-size: 13px; font-weight: 600;">{value}</div>
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
