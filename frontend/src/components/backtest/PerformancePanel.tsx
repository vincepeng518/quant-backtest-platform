'use client';

import React, { useMemo, useState, useCallback } from 'react';
import { PerformanceMetrics, EquityPoint, TradeRecord, PositionStatusPoint } from '@/types/api';
import { EquityPnlChart } from '@/components/charts/EquityPnlChart';
import { Tooltip } from '@/components/ui/Tooltip';
import {
  TV_UP, TV_DOWN,
  safeFmt, safePct, safeSigned, safeInt,
} from '@/lib/format';

interface PerformancePanelProps {
  metrics: PerformanceMetrics;
  equity: EquityPoint[];
  buyHold?: EquityPoint[];
  trades?: TradeRecord[];
  positionStatus?: PositionStatusPoint[];
  initialCapital: number;
  onSelectTrade?: (trade: TradeRecord | null) => void;
}

// ── Inline SVG Sparkline ──
const EquitySparkline: React.FC<{ data: EquityPoint[]; width?: number; height?: number }> = ({
  data,
  width = 100,
  height = 28,
}) => {
  if (!data || data.length < 2) return null;
  const values = data.map((d) => d.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pad = 2;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((v - min) / range) * (height - pad * 2) - pad;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const color = values[values.length - 1] >= values[0] ? TV_UP : TV_DOWN;
  const fillColor = values[values.length - 1] >= values[0] ? 'rgba(8,153,129,0.08)' : 'rgba(242,54,69,0.08)';
  const area = `${pts}`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="shrink-0 opacity-80">
      <defs>
        <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.15" />
          <stop offset="100%" stopColor={color} stopOpacity="0.01" />
        </linearGradient>
      </defs>
      <polyline fill="none" stroke={color} strokeWidth={1.2} points={pts} />
      <polygon fill="url(#spark-fill)" points={`0,${height} ${pts} ${width},${height}`} />
    </svg>
  );
};

// ── TV-style KPI Block ──
interface KpiBlockProps {
  label: string;
  value: string;
  sub?: string;
  color?: 'pos' | 'neg' | 'neutral' | 'inherit';
  tip?: string;
  mega?: boolean;
  sparkline?: React.ReactNode;
}

const KpiBlock: React.FC<KpiBlockProps> = ({ label, value, sub, color = 'inherit', tip, mega, sparkline }) => {
  const colorClass =
    color === 'pos' ? 'text-[#089981]' : color === 'neg' ? 'text-[#f23645]' : 'text-[#d1d4dc]';
  const valueSize = mega ? 'text-xl sm:text-2xl' : 'text-sm sm:text-base';
  const subSize = mega ? 'text-xs' : 'text-[10px]';

  const inner = (
    <div
      className={`group relative bg-[#161a25] px-3 sm:px-4 py-2.5 sm:py-3 flex flex-col gap-0.5 select-none card-lift cursor-default min-w-0 border border-[#363c4e]/15 hover:border-[#363c4e]/40 rounded-sm ${
        mega ? 'py-3 sm:py-4' : ''
      }`}
    >
      <div className="flex items-center justify-between gap-2 min-w-0">
        <span className="text-[10px] font-medium text-[#787b86] uppercase tracking-wider truncate">
          {label}
        </span>
        {sparkline && <div className="shrink-0">{sparkline}</div>}
      </div>
      <span className={`${valueSize} font-mono font-semibold tracking-tight tabular-nums truncate ${colorClass}`}>
        {value}
      </span>
      {sub != null && (
        <span className={`${subSize} font-mono tabular-nums ${colorClass} opacity-70 truncate`}>{sub}</span>
      )}
    </div>
  );

  if (tip) {
    return <Tooltip content={tip} position="top">{inner}</Tooltip>;
  }
  return inner;
};

// ── Section Header ──
const SectionHeader: React.FC<{ title: string }> = ({ title }) => (
  <div className="col-span-full bg-[#161a25] px-4 pt-3 pb-1">
    <span className="text-[9px] font-semibold uppercase tracking-[0.12em] text-[#787b86]">
      {title}
    </span>
  </div>
);

// ── Toggle Button (TV style) ──
const ToggleBtn: React.FC<{
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}> = ({ active, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    className={`px-2.5 py-1 rounded text-[10px] font-mono border transition-colors duration-150 active:scale-[0.97] ${
      active
        ? 'border-[#089981]/40 bg-[#089981]/10 text-[#089981]'
        : 'border-[#363c4e]/30 text-[#787b86] hover:text-[#d1d4dc]'
    }`}
  >
    {children}
  </button>
);

// ── Main Component ──
export const PerformancePanel: React.FC<PerformancePanelProps> = ({
  metrics,
  equity,
  buyHold = [],
  trades = [],
  positionStatus = [],
  initialCapital,
  onSelectTrade,
}) => {
  const [showEquity, setShowEquity] = useState(true);
  const [showBuyHold, setShowBuyHold] = useState(false);
  const [showPnl, setShowPnl] = useState(true);
  const [showGainDd, setShowGainDd] = useState(true);
  const [showSpread, setShowSpread] = useState(false);

  const m = metrics as any;
  const netProfit = Number(m.net_profit ?? 0);
  const totalReturnPct = Number(m.total_return_pct ?? 0);
  const annualReturnPct = Number(m.annual_return_pct ?? 0);
  const maxDdPct = Number(m.max_drawdown_pct ?? 0);
  const maxDdAmount = Number(m.max_drawdown ?? 0);
  const sharpeRatio = Number(m.sharpe_ratio ?? 0);
  const sortinoRatio = Number(m.sortino_ratio ?? 0);
  const calmar = Number(m.calmar_ratio ?? 0);
  const volatility = Number(m.volatility ?? 0);
  const winRate = Number(m.win_rate ?? 0);
  const winningTrades = Number(m.winning_trades ?? 0);
  const losingTrades = Number(m.losing_trades ?? 0);
  const totalTrades = Number(m.total_trades ?? 0);
  const profitFactor = Number(m.profit_factor ?? 0);
  const largestWin = Number(m.largest_win ?? 0);
  const largestLoss = Number(m.largest_loss ?? 0);
  const winLossRatio = Number(m.win_loss_ratio ?? 0);
  const expectancy = Number(m.expectancy ?? 0);
  const avgHoldingBars = Number(m.avg_holding_bars ?? 0);
  const tradeFreq = Number(m.trade_freq ?? 0);
  const avgWin = Number(m.avg_win ?? 0);
  const avgLoss = Number(m.avg_loss ?? 0);
  const maxDdDuration = Number(m.max_drawdown_duration ?? 0);

  // ── Status bar segments ──
  const statusSegments = useMemo(() => {
    if (!positionStatus || positionStatus.length === 0 || equity.length === 0) return [];
    const t0 = equity[0].time;
    const t1 = equity[equity.length - 1].time;
    const span = t1 - t0;
    if (span <= 0) return [];
    const segs = positionStatus
      .map((s) => ({ time: toUnixSec(s.time), state: s.state }))
      .filter((s) => Number.isFinite(s.time) && s.time > 0)
      .sort((a, b) => a.time - b.time);
    const out: { left: number; width: number; color: string }[] = [];
    for (let i = 0; i < segs.length; i++) {
      const start = Math.max(segs[i].time, t0);
      const end = i + 1 < segs.length ? Math.min(segs[i + 1].time, t1) : t1;
      const left = ((start - t0) / span) * 100;
      const width = ((end - start) / span) * 100;
      if (width <= 0) continue;
      const color =
        segs[i].state === 'long' ? TV_UP : segs[i].state === 'short' ? TV_DOWN : 'transparent';
      out.push({ left, width, color });
    }
    return out;
  }, [positionStatus, equity]);

  // ── Handle trade hover for cross-component linking ──
  // (Currently placeholder — wired up via page.tsx)
  const handleTradeHover = useCallback(
    (trade: TradeRecord | null) => {
      onSelectTrade?.(trade);
    },
    [onSelectTrade]
  );

  // ── 進階風險指標 (純前端, 從 equity + trades 算) ──
  const adv = useMemo(() => calcAdvRisk(equity, trades), [equity, trades]);

  // ── #2 擴充指標 (純前端: Rolling Sharpe / 超額 α / β-相關) ──
  const ext = useMemo(() => calcExtMetrics(equity, buyHold), [equity, buyHold]);

  const fmtPct = (v: number | null, d = 2): string =>
    v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)}%`;
  const fmtNum = (v: number | null, d = 3): string =>
    v == null ? '—' : v.toFixed(d);

  return (
    <div className="bg-[#161a25] border-t border-[#363c4e]/10">
      {/* ── Mega KPIs Row ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-[#363c4e]/20 border-b border-[#363c4e]/10">
        <KpiBlock
          label="總損益 Net Profit"
          value={safeSigned(netProfit)}
          sub={safePct(totalReturnPct)}
          color={netProfit >= 0 ? 'pos' : 'neg'}
          mega
          tip="Net Profit：所有平倉交易盈虧總和（= 期末權益 − 初始資金）"
          sparkline={<EquitySparkline data={equity} />}
        />
        <KpiBlock
          label="夏普比率 Sharpe"
          value={safeFmt(sharpeRatio)}
          color={sharpeRatio >= 1 ? 'pos' : sharpeRatio >= 0 ? 'neutral' : 'neg'}
          mega
          tip="Sharpe Ratio：超額報酬 / 報酬標準差。>1 為佳，>2 優秀，>3 卓越"
        />
        <KpiBlock
          label="最大回撤 Max DD"
          value={safePct(maxDdPct, { signed: false })}
          sub={`${safeFmt(maxDdAmount)} USDT`}
          color="neg"
          mega
          tip="Max Drawdown：權益曲線從歷史峰值到谷值的最大跌幅"
        />
        <KpiBlock
          label="獲利因子 PF"
          value={safeFmt(profitFactor)}
          color={profitFactor >= 1.5 ? 'pos' : profitFactor >= 1 ? 'neutral' : 'neg'}
          mega
          tip="Profit Factor：總毛利 / 總毛損（絕對值）。>1 表示系統盈利，>1.5 優秀"
        />
      </div>

      {/* ── Mega KPIs Row 2 ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-[#363c4e]/20 border-b border-[#363c4e]/10">
        <KpiBlock
          label="勝率 Win Rate"
          value={safePct(winRate, { signed: false })}
          sub={`${safeInt(winningTrades)}W / ${safeInt(losingTrades)}L`}
          color={winRate >= 50 ? 'pos' : 'neutral'}
          mega
          tip="Win Rate：獲利交易數 / 總交易數"
        />
        <KpiBlock
          label="期望值 Expectancy"
          value={safeSigned(expectancy)}
          sub="每筆期望 PnL"
          color={expectancy >= 0 ? 'pos' : 'neg'}
          mega
          tip="Expectancy：勝率×均盈 − 敗率×均虧。單筆交易的平均期望盈虧"
        />
        <KpiBlock
          label="總交易數 Total Trades"
          value={safeInt(totalTrades)}
          sub={`${safeInt(winningTrades)}W / ${safeInt(losingTrades)}L`}
          color="neutral"
          mega
          tip="Total Trades：測試區間內產生的所有交易（含未平倉）"
        />
        <KpiBlock
          label="年化回報 Annual"
          value={safePct(annualReturnPct)}
          color={annualReturnPct >= 0 ? 'pos' : 'neg'}
          mega
          tip="Annualized Return：以測試區間天數年化（CAGR）的複合年增率"
        />
      </div>

      {/* ── 回報類 (Returns) ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-[#363c4e]/20 border-b border-[#363c4e]/10">
        <SectionHeader title="回報類 Returns" />
        <KpiBlock
          label="年化回報 Annual Return"
          value={safePct(annualReturnPct)}
          color={annualReturnPct >= 0 ? 'pos' : 'neg'}
          tip="Annualized Return：以測試區間天數年化（CAGR）的複合年增率"
        />
        <KpiBlock
          label="索提諾比率 Sortino"
          value={safeFmt(sortinoRatio)}
          color={sortinoRatio >= 1 ? 'pos' : sortinoRatio >= 0 ? 'neutral' : 'neg'}
          tip="Sortino Ratio：超額報酬 / 下行風險。只計入負向波動，比夏普更精準"
        />
        <KpiBlock
          label="波動率 Volatility"
          value={safePct(Number.isFinite(volatility) && Math.abs(volatility) <= 5 ? volatility * 100 : volatility, { signed: false })}
          color="neutral"
          tip="Volatility：策略日報酬的標準差（年化），衡量波動風險"
        />
        <KpiBlock
          label="最差回撤期 Max DD Duration"
          value={safeInt(maxDdDuration)}
          sub="根 K 線"
          color="neutral"
          tip="Max Drawdown Duration：從峰值到恢復並創新高所需的最長 K 線數"
        />
      </div>

      {/* ── 風險類 (Risk) ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-[#363c4e]/20 border-b border-[#363c4e]/10">
        <SectionHeader title="風險類 Risk" />
        <KpiBlock
          label="卡瑪比率 Calmar"
          value={safeFmt(calmar)}
          sub="年化/最大回撤"
          color={calmar >= 1 ? 'pos' : calmar >= 0 ? 'neutral' : 'neg'}
          tip="Calmar Ratio：年化回報 / 最大回撤。越高代表回撤控制越好"
        />
        <KpiBlock
          label="獲利因子 Profit Factor"
          value={safeFmt(profitFactor)}
          color={profitFactor >= 1.5 ? 'pos' : profitFactor >= 1 ? 'neutral' : 'neg'}
          tip="Profit Factor：總毛利 / 總毛損（絕對值）。>1 表示系統盈利，>1.5 優秀"
        />
        <KpiBlock
          label="盈虧比 Payoff Ratio"
          value={safeFmt(winLossRatio)}
          sub="均盈/均虧"
          color={winLossRatio >= 1.5 ? 'pos' : winLossRatio >= 1 ? 'neutral' : 'neg'}
          tip="Payoff Ratio：平均盈利 / 平均虧損。>1 代表每虧 1 元能賺回更多"
        />
        <KpiBlock
          label="期望值 Expectancy"
          value={safeSigned(expectancy)}
          sub="每筆期望 PnL"
          color={expectancy >= 0 ? 'pos' : 'neg'}
          tip="Expectancy：勝率×均盈 − 敗率×均虧。單筆交易的平均期望盈虧"
        />
      </div>

      {/* ── 交易類 (Trades) ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-[#363c4e]/20 border-b border-[#363c4e]/10">
        <SectionHeader title="交易類 Trades" />
        <KpiBlock
          label="總交易數 Total Trades"
          value={safeInt(totalTrades)}
          sub={`${safeInt(winningTrades)}W / ${safeInt(losingTrades)}L`}
          color="neutral"
          tip="Total Trades：測試區間內產生的所有交易（含未平倉）"
        />
        <KpiBlock
          label="平均盈利 Avg Win"
          value={safeSigned(avgWin)}
          color="pos"
          tip="Average Winning Trade：所有獲利交易的平均盈餘"
        />
        <KpiBlock
          label="平均虧損 Avg Loss"
          value={safeFmt(avgLoss)}
          color="neg"
          tip="Average Losing Trade：所有虧損交易的平均虧損"
        />
        <KpiBlock
          label="最大單筆盈利 Largest Win"
          value={safeSigned(largestWin)}
          color="pos"
          tip="Largest Winning Trade：單筆最大盈利金額"
        />
        <KpiBlock
          label="最大單筆虧損 Largest Loss"
          value={safeFmt(largestLoss)}
          color="neg"
          tip="Largest Losing Trade：單筆最大虧損金額"
        />
        <KpiBlock
          label="平均持倉 Avg Holding"
          value={safeFmt(avgHoldingBars, 1)}
          sub="根 K 線"
          color="neutral"
          tip="Avg Holding Period：每筆交易平均持有的 K 線數"
        />
        <KpiBlock
          label="交易頻率 Trade Freq"
          value={safeFmt(tradeFreq)}
          sub="筆/日"
          color="neutral"
          tip="Trade Frequency：測試區間內平均每天產生的交易筆數"
        />
      </div>

      {/* ── #2 擴充指標 (Rolling Sharpe / 超額 α / β-相關) ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-[#363c4e]/20 border-b border-[#363c4e]/10">
        <SectionHeader title="擴充指標 Extended" />
        <KpiBlock
          label="Rolling 30D Sharpe"
          value={fmtNum(ext.rollSharpe)}
          sub="近30根K線"
          color={ext.rollSharpe == null ? 'neutral' : ext.rollSharpe >= 1 ? 'pos' : ext.rollSharpe >= 0 ? 'neutral' : 'neg'}
          tip="Rolling Sharpe：以最近 30 根 K 線收益窗口計算的滾動夏普比率，反映近期穩定性"
        />
        <KpiBlock
          label="超額收益 α"
          value={fmtPct(ext.alphaPct)}
          sub={ext.alphaPct == null ? 'vs 基準' : 'vs 買進持有'}
          color={ext.alphaPct == null ? 'neutral' : ext.alphaPct >= 0 ? 'pos' : 'neg'}
          tip="Alpha (α)：策略總回報 − 買進持有基準總回報。>0 代表策略戰勝單純持有"
        />
        <KpiBlock
          label="相關性 β"
          value={fmtNum(ext.beta)}
          sub={ext.beta == null ? 'vs 基準' : `ρ=${ext.corr?.toFixed(2)}`}
          color={ext.beta == null ? 'neutral' : ext.beta <= 0.5 ? 'pos' : ext.beta <= 1 ? 'neutral' : 'neg'}
          tip="Beta (β)：策略收益對基準收益的敏感度。ρ 為相關係數。β 低代表與大盤脫鉤、分散效果好"
        />
        <KpiBlock
          label="超額夏普 ExSharpe"
          value={fmtNum(ext.exSharpe)}
          sub="策略−基準"
          color={ext.exSharpe == null ? 'neutral' : ext.exSharpe >= 0 ? 'pos' : 'neg'}
          tip="Excess Sharpe：策略 Sharpe − 基準 Sharpe。衡量風險調整後的超額能力"
        />
      </div>

      {/* ── 進階風險指標 (用戶指定 13 項) ── */}
      <div className="border-t border-[#363c4e]/10 px-4 py-4">
        <p className="text-xs text-textSecondary mb-2 font-medium">進階風險指標 · Advanced Risk Metrics</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-px bg-[#363c4e]/20">
          <KpiBlock label="短期勝率 <24K" value={adv.tfWinShort == null ? '—' : `${adv.tfWinShort.toFixed(1)}%`} color={adv.tfWinShort == null ? 'neutral' : adv.tfWinShort >= 50 ? 'pos' : 'neg'} tip="持有 <24 根 K 線的交易勝率" />
          <KpiBlock label="中期勝率 24-96K" value={adv.tfWinMid == null ? '—' : `${adv.tfWinMid.toFixed(1)}%`} color={adv.tfWinMid == null ? 'neutral' : adv.tfWinMid >= 50 ? 'pos' : 'neg'} tip="持有 24-96 根 K 線的交易勝率" />
          <KpiBlock label="長期勝率 >96K" value={adv.tfWinLong == null ? '—' : `${adv.tfWinLong.toFixed(1)}%`} color={adv.tfWinLong == null ? 'neutral' : adv.tfWinLong >= 50 ? 'pos' : 'neg'} tip="持有 >96 根 K 線的交易勝率" />
          <KpiBlock label="最大回撤天數" value={`${adv.maxDdDays}`} sub="天" color="neutral" tip="資金曲線連續處於回撤狀態的最長天數" />
          <KpiBlock label="恢復因子" value={fmtNum(adv.recoveryFactor)} color={adv.recoveryFactor == null ? 'neutral' : adv.recoveryFactor >= 1 ? 'pos' : 'neg'} tip="期末權益 / 區間最低權益 (越高恢復越快)" />
          <KpiBlock label="偏度 Skew" value={fmtNum(adv.skew)} color={adv.skew == null ? 'neutral' : adv.skew > 0 ? 'pos' : 'neg'} tip="收益分布偏度：正=右偏(偶有暴利)，負=左偏(偶有暴虧)" />
          <KpiBlock label="峰度 Kurt" value={fmtNum(adv.kurt)} color={adv.kurt == null ? 'neutral' : adv.kurt > 0 ? 'neg' : 'pos'} tip="超額峰度：正=肥尾(極端風險高)" />
          <KpiBlock label="VaR 95%" value={adv.var95 == null ? '—' : safePct(adv.var95 * 100)} color="neg" tip="每日收益 95% 置信度的歷史 VaR (最大單日虧損分位)" />
          <KpiBlock label="CVaR 95%" value={adv.cvar95 == null ? '—' : safePct(adv.cvar95 * 100)} color="neg" tip="VaR 95% 條件下平均虧損 (尾部期望)" />
          <KpiBlock label="VaR 99%" value={adv.var99 == null ? '—' : safePct(adv.var99 * 100)} color="neg" tip="每日收益 99% 置信度的歷史 VaR" />
          <KpiBlock label="CVaR 99%" value={adv.cvar99 == null ? '—' : safePct(adv.cvar99 * 100)} color="neg" tip="VaR 99% 條件下平均虧損 (極端尾部期望)" />
          <KpiBlock label="最差月份" value={fmtPct(adv.worstMonth)} color="neg" tip="月度收益最低的一個月" />
          <KpiBlock label="最佳月份" value={fmtPct(adv.bestMonth)} color="pos" tip="月度收益最高的一個月" />
          <KpiBlock label="正報酬月比例" value={adv.posMonthPct == null ? '—' : `${adv.posMonthPct.toFixed(1)}%`} color={adv.posMonthPct == null ? 'neutral' : adv.posMonthPct >= 50 ? 'pos' : 'neg'} tip="正報酬月份佔所有有交易月份的比例" />
        </div>
      </div>

      {/* ── Legend / Control Panel ── */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-t border-[#363c4e]/10">
        <ToggleBtn active={showEquity} onClick={() => setShowEquity((v) => !v)}>
          累計損益
        </ToggleBtn>
        <ToggleBtn active={showBuyHold} onClick={() => setShowBuyHold((v) => !v)}>
          {showBuyHold ? '隱藏' : '顯示'} 買進並持有
        </ToggleBtn>
        <ToggleBtn active={showPnl} onClick={() => setShowPnl((v) => !v)}>
          單筆盈虧
        </ToggleBtn>
        <ToggleBtn active={showGainDd} onClick={() => setShowGainDd((v) => !v)}>
          漲幅與回撤
        </ToggleBtn>
        <ToggleBtn active={showSpread} onClick={() => setShowSpread((v) => !v)}>
          {showSpread ? '隱藏' : '顯示'} 策略−基準
        </ToggleBtn>
      </div>

      {/* ── Status bar ── */}
      {statusSegments.length > 0 && (
        <div className="relative h-1 w-full bg-transparent px-0">
          <div className="absolute inset-0 flex">
            {statusSegments.map((s, i) => (
              <div
                key={i}
                style={{
                  position: 'absolute',
                  left: `${s.left}%`,
                  width: `${s.width}%`,
                  backgroundColor: s.color,
                  height: '100%',
                  opacity: 0.6,
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* ── Main Chart ── */}
      <EquityPnlChart
        equity={showEquity ? equity : []}
        buyHold={buyHold}
        trades={showPnl ? trades : []}
        initialCapital={initialCapital}
        showBuyHold={showBuyHold}
        showSpread={showSpread}
        theme="dark"
      />
    </div>
  );
};

// ── Helper ──
const toUnixSec = (v: any): number => {
  if (v == null) return 0;
  if (typeof v === 'number') return v;
  const ms = Date.parse(v);
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : 0;
};

// ── 進階風險指標 (純前端計算, 來源: equity curve + trades) ──
interface AdvRisk {
  tfWinShort: number | null;
  tfWinMid: number | null;
  tfWinLong: number | null;
  maxDdDays: number;
  recoveryFactor: number | null;
  skew: number | null;
  kurt: number | null;
  var95: number | null;
  cvar95: number | null;
  var99: number | null;
  cvar99: number | null;
  worstMonth: number | null;
  bestMonth: number | null;
  posMonthPct: number | null;
}

function calcAdvRisk(equity: EquityPoint[], trades: TradeRecord[]): AdvRisk {
  const empty: AdvRisk = {
    tfWinShort: null, tfWinMid: null, tfWinLong: null,
    maxDdDays: 0, recoveryFactor: null, skew: null, kurt: null,
    var95: null, cvar95: null, var99: null, cvar99: null,
    worstMonth: null, bestMonth: null, posMonthPct: null,
  };
  if (!equity || equity.length < 3) return empty;

  // 日收益率 (從 equity 差分)
  const eq = equity.map((e) => Number(e.equity) || 0).filter((v) => v > 0);
  const rets: number[] = [];
  for (let i = 1; i < eq.length; i++) {
    const prev = eq[i - 1];
    if (prev > 0) rets.push((eq[i] - prev) / prev);
  }
  const n = rets.length;

  // 偏度 / 峰度
  let skew: number | null = null, kurt: number | null = null;
  if (n >= 3) {
    const mean = rets.reduce((a, b) => a + b, 0) / n;
    const variance = rets.reduce((a, b) => a + (b - mean) ** 2, 0) / n;
    const std = Math.sqrt(variance);
    if (std > 0) {
      const m3 = rets.reduce((a, b) => a + ((b - mean) / std) ** 3, 0) / n;
      const m4 = rets.reduce((a, b) => a + ((b - mean) / std) ** 4, 0) / n;
      skew = m3;
      kurt = m4 - 3; // excess kurtosis
    }
  }

  // VaR / CVaR (歷史模擬法, 用負收益分位)
  const negRets = rets.filter((r) => r < 0).sort((a, b) => a - b);
  const quantile = (arr: number[], q: number): number | null => {
    if (arr.length === 0) return null;
    const idx = Math.floor(q * arr.length);
    return arr[Math.min(idx, arr.length - 1)];
  };
  const meanArr = (arr: number[], start: number): number => {
    const sub = arr.slice(start);
    return sub.length ? sub.reduce((a, b) => a + b, 0) / sub.length : 0;
  };
  const var95 = negRets.length ? quantile(negRets, 0.05) : null;
  const var99 = negRets.length ? quantile(negRets, 0.01) : null;
  const cvar95 = negRets.length ? meanArr(negRets, Math.floor(0.05 * negRets.length)) : null;
  const cvar99 = negRets.length ? meanArr(negRets, Math.floor(0.01 * negRets.length)) : null;

  // 最大回撤持續天數 (equity drawdown 連續 >0 最長期間, 按 timestamp 差算天)
  let maxDdDays = 0;
  let curDays = 0;
  let prevT = 0;
  for (let i = 0; i < equity.length; i++) {
    const e = equity[i];
    const dd = Number(e.drawdown) || 0;
    const t = Number(e.timestamp) || Number(e.time) || 0;
    if (dd > 0) {
      if (prevT > 0 && t > prevT) {
        curDays += Math.max(1, Math.round((t - prevT) / 86400));
      } else {
        curDays += 1;
      }
      maxDdDays = Math.max(maxDdDays, curDays);
    } else {
      curDays = 0;
    }
    prevT = t;
  }

  // 恢復因子 (期末/最低點, 或 peak/trough)
  const minEq = Math.min(...eq);
  const lastEq = eq[eq.length - 1];
  const recoveryFactor = minEq > 0 ? lastEq / minEq : null;

  // 時間週期勝率 (按 trades holding_bars 分桶: <24短 / 24-96中 / >96長)
  const bucketWin = (lo: number, hi: number): number | null => {
    const sub = trades.filter((t) => {
      const hb = Number((t as any).holding_bars ?? 0);
      return hb >= lo && hb < hi;
    });
    if (sub.length === 0) return null;
    const wins = sub.filter((t) => Number((t as any).pnl ?? (t as any).pnl_pct ?? 0) > 0).length;
    return (wins / sub.length) * 100;
  };
  const tfWinShort = bucketWin(0, 24);
  const tfWinMid = bucketWin(24, 96);
  const tfWinLong = bucketWin(96, Infinity);

  // 月度收益 (equity 按月聚合)
  const monthMap = new Map<string, number>();
  for (let i = 1; i < equity.length; i++) {
    const t = Number(equity[i].timestamp) || Number(equity[i].time) || 0;
    const d = new Date(t * 1000);
    if (!Number.isFinite(d.getTime())) continue;
    const key = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
    const prev = eq[i - 1];
    const cur = eq[i];
    monthMap.set(key, (monthMap.get(key) ?? 0) + (prev > 0 ? (cur - prev) / prev : 0));
  }
  const months = Array.from(monthMap.values());
  let worstMonth: number | null = null, bestMonth: number | null = null, posMonthPct: number | null = null;
  if (months.length > 0) {
    worstMonth = Math.min(...months) * 100;
    bestMonth = Math.max(...months) * 100;
    posMonthPct = (months.filter((m) => m > 0).length / months.length) * 100;
  }

  return {
    tfWinShort, tfWinMid, tfWinLong, maxDdDays, recoveryFactor,
    skew, kurt, var95, cvar95, var99, cvar99,
    worstMonth, bestMonth, posMonthPct,
  };
};

// ── #2 擴充指標: 純前端從 equity + buyHold 算 ──
interface ExtMetrics {
  rollSharpe: number | null;
  alphaPct: number | null;
  beta: number | null;
  corr: number | null;
  exSharpe: number | null;
}

function calcExtMetrics(equity: EquityPoint[], buyHold: EquityPoint[]): ExtMetrics {
  const empty: ExtMetrics = { rollSharpe: null, alphaPct: null, beta: null, corr: null, exSharpe: null };
  if (!equity || equity.length < 5) return empty;

  // 策略日收益序列
  const stratEq = equity.map((e) => Number(e.equity) || 0).filter((v) => v > 0);
  const stratRets: number[] = [];
  for (let i = 1; i < stratEq.length; i++) {
    const prev = stratEq[i - 1];
    if (prev > 0) stratRets.push((stratEq[i] - prev) / prev);
  }
  const n = stratRets.length;
  if (n < 3) return empty;

  const mean = (a: number[]) => a.reduce((x, y) => x + y, 0) / a.length;
  const std = (a: number[]) => {
    const m = mean(a);
    return Math.sqrt(a.reduce((x, y) => x + (y - m) ** 2, 0) / a.length);
  };

  // Rolling 30 窗口 Sharpe (取最後一個完整窗口)
  const W = Math.min(30, n);
  let rollSharpe: number | null = null;
  if (W >= 3) {
    const win = stratRets.slice(n - W);
    const wm = mean(win);
    const ws = std(win);
    if (ws > 0) {
      const periodsPerYear = 252; // 假設日頻近似
      rollSharpe = (wm / ws) * Math.sqrt(periodsPerYear);
    }
  }

  // 基準對比 (buyHold 需同長度對齊)
  if (!buyHold || buyHold.length < 5) return { rollSharpe, alphaPct: null, beta: null, corr: null, exSharpe: null };

  // 對齊時間戳
  const toTs = (e: any) => Number(e.time ?? e.timestamp ?? 0);
  const bhMap = new Map<number, number>();
  for (const e of buyHold) {
    const t = toTs(e);
    if (t > 0) bhMap.set(t, Number(e.equity) || 0);
  }
  const stratMap = new Map<number, number>();
  for (const e of equity) {
    const t = toTs(e);
    if (t > 0) stratMap.set(t, Number(e.equity) || 0);
  }
  const commonT = Array.from(stratMap.keys()).filter((t) => bhMap.has(t)).sort((a, b) => a - b);
  if (commonT.length < 5) return { rollSharpe, alphaPct: null, beta: null, corr: null, exSharpe: null };

  // 對齊後的收益序列
  const sRets: number[] = [];
  const bRets: number[] = [];
  for (let i = 1; i < commonT.length; i++) {
    const sp = stratMap.get(commonT[i - 1])!;
    const sc = stratMap.get(commonT[i])!;
    const bp = bhMap.get(commonT[i - 1])!;
    const bc = bhMap.get(commonT[i])!;
    if (sp > 0 && bp > 0) {
      sRets.push((sc - sp) / sp);
      bRets.push((bc - bp) / bp);
    }
  }
  if (sRets.length < 3) return { rollSharpe, alphaPct: null, beta: null, corr: null, exSharpe: null };

  // Alpha: 總回報差
  const stratTotal = (stratEq[stratEq.length - 1] / stratEq[0] - 1) * 100;
  const bhEq = buyHold.map((e) => Number(e.equity) || 0).filter((v) => v > 0);
  const bhTotal = bhEq.length > 1 ? (bhEq[bhEq.length - 1] / bhEq[0] - 1) * 100 : 0;
  const alphaPct = stratTotal - bhTotal;

  // Beta + 相關係數
  const ms = mean(sRets), mb = mean(bRets);
  const cov = sRets.reduce((acc, s, i) => acc + (s - ms) * (bRets[i] - mb), 0) / sRets.length;
  const varB = std(bRets) ** 2;
  const beta = varB > 0 ? cov / varB : null;
  const corr = std(sRets) > 0 && std(bRets) > 0
    ? cov / (std(sRets) * std(bRets))
    : null;

  // Excess Sharpe (策略 − 基準)
  const sStd = std(sRets), bStd = std(bRets);
  const stratSharpe = sStd > 0 ? (ms / sStd) * Math.sqrt(252) : 0;
  const bhSharpe = bStd > 0 ? (mb / bStd) * Math.sqrt(252) : 0;
  const exSharpe = stratSharpe - bhSharpe;

  return { rollSharpe, alphaPct, beta, corr, exSharpe };
}