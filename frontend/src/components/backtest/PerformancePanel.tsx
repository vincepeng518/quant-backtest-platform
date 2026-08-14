'use client';

import React, { useMemo, useState, useCallback, useId } from 'react';
import { PerformanceMetrics, EquityPoint, TradeRecord, PositionStatusPoint } from '@/types/api';
import { EquityPnlChart } from '@/components/charts/EquityPnlChart';
import { Tooltip } from '@/components/ui/Tooltip';
import { StatTable, StatRow } from '@/components/backtest/StatTable';
import {
  TV_UP, TV_DOWN,
  safeFmt, safePct, safeSigned, safeInt, fmtProfitFactor,
} from '@/lib/format';

interface PerformancePanelProps {
  metrics: PerformanceMetrics;
  equity: EquityPoint[];
  buyHold?: EquityPoint[];
  trades?: TradeRecord[];
  positionStatus?: PositionStatusPoint[];
  initialCapital: number;
  currency?: string; // 結算幣種(USDT/USD),由 Asset Class 決定,全介面單位連動
  onSelectTrade?: (trade: TradeRecord | null) => void;
}

// ── Inline SVG Sparkline ──
const EquitySparkline: React.FC<{ data: EquityPoint[]; width?: number; height?: number }> = ({
  data,
  width = 100,
  height = 28,
}) => {
  const gid = useId();
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
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="shrink-0 opacity-80">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.18" />
          <stop offset="100%" stopColor={color} stopOpacity="0.01" />
        </linearGradient>
      </defs>
      <polyline fill="none" stroke={color} strokeWidth={1.2} points={pts} />
      <polygon fill={`url(#${gid})`} points={`0,${height} ${pts} ${width},${height}`} />
    </svg>
  );
};


type TabId = 'overview' | 'performance' | 'trades' | 'risk';

// ── Quality Score Banner (回測評分) ──
const GRADE_COLORS: Record<string, string> = {
  S: '#e8b339', A: '#22c55e', B: '#3b82f6', C: '#eab308', D: '#f97316', F: '#ef4444',
};

const QualityScoreBanner: React.FC<{
  score: number;
  grade: string;
  breakdown: {
    sharpe: number; profit_factor: number; win_rate: number;
    drawdown: number; sample: number;
    raw_score: number; confidence: number;
    cap: number; final_score: number;
    cap_applied?: boolean; loss_cap_applied?: boolean;
    penalty_reason: string | null;
  };
}> = ({ score, grade, breakdown }) => {
  const gc = GRADE_COLORS[grade] ?? '#ef4444';
  const b = breakdown;
  const dims = [
    { label: 'Sharpe', v: b.sharpe ?? 0, weight: '30%' },
    { label: '獲利因子', v: b.profit_factor ?? 0, weight: '25%' },
    { label: '勝率', v: b.win_rate ?? 0, weight: '15%' },
    { label: '低回撤', v: b.drawdown ?? 0, weight: '20%' },
    { label: '樣本數', v: b.sample ?? 0, weight: '10%' },
  ];

  // 扣分鏈: 用後端回傳的 *_applied flag 判斷哪幾步真的削到分數
  const conf = b.confidence ?? 1;
  const rawScore = b.raw_score ?? score;
  const capVal = b.cap ?? 100;
  const capOn = b.cap_applied ?? (capVal < rawScore);
  const lossOn = b.loss_cap_applied ?? false;
  const chainParts: string[] = [];
  if (conf < 1.0) chainParts.push(`×${conf.toFixed(2)}`);
  if (capOn) chainParts.push(`cap ${capVal.toFixed(1)}`);
  if (lossOn) chainParts.push('封頂 65');
  const chainText = chainParts.length
    ? `${rawScore.toFixed(1)} → ${chainParts.join(' → ')} → ${score.toFixed(1)}`
    : null;

  return (
    <div className="flex items-center gap-4 px-4 sm:px-5 py-3 border-b border-border/12 bg-surface">
      {/* Grade 大圓 */}
      <div
        className="shrink-0 w-12 h-12 rounded-full flex items-center justify-center text-xl font-bold font-mono"
        style={{ backgroundColor: `${gc}1a`, color: gc, border: `2px solid ${gc}` }}
      >
        {grade}
      </div>
      {/* 分數 + 標題 */}
      <div className="shrink-0 min-w-[90px]">
        <div className="text-[10px] uppercase tracking-[0.08em] text-textSecondary">回測評分</div>
        <div className="text-[22px] font-mono font-semibold leading-none" style={{ color: gc }}>
          {score.toFixed(1)}
          <span className="text-xs text-textSecondary ml-0.5">/100</span>
        </div>
        {chainText && (
          <div className="text-[8px] text-textSecondary mt-0.5 leading-tight font-mono opacity-70">{chainText}</div>
        )}
        {b.penalty_reason && (
          <div className="text-[9px] text-textSecondary mt-0.5 leading-tight">{b.penalty_reason}</div>
        )}
      </div>
      {/* 5 維度進度條 */}
      <div className="flex-1 grid grid-cols-2 sm:grid-cols-5 gap-2 min-w-0">
        {dims.map((d) => (
          <div key={d.label} className="min-w-0">
            <div className="flex justify-between text-[9px] font-mono text-textSecondary mb-0.5">
              <span className="truncate">{d.label}</span>
              <span className="opacity-80">{d.weight}</span>
            </div>
            <div className="h-1 w-full bg-border/20 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${d.v}%`, backgroundColor: d.v >= 70 ? '#22c55e' : d.v >= 40 ? '#eab308' : '#ef4444' }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ── Hero KPI (TV Strategy Tester top strip) ──
const HeroKpi: React.FC<{
  label: string;
  en: string;
  value: string;
  sub?: string;
  color?: 'pos' | 'neg' | 'neutral';
  spark?: React.ReactNode;
}> = ({ label, en, value, sub, color = 'neutral', spark }) => {
  const c = color === 'pos' ? 'text-success' : color === 'neg' ? 'text-danger' : 'text-text';
  return (
    <div className="relative px-4 sm:px-5 py-3.5 border-r border-border/12 last:border-r-0 min-w-0 group overflow-hidden">
      {/* sparkline sits behind, absolutely positioned so it can't shift the numbers */}
      {spark && (
        <div className="absolute top-2.5 right-3 opacity-40 group-hover:opacity-70 transition-opacity pointer-events-none">
          {spark}
        </div>
      )}
      <div className="flex items-baseline gap-1.5 min-w-0 h-[14px] mb-1.5">
        <span className="text-[10px] uppercase tracking-[0.08em] text-textSecondary truncate">
          {label}
        </span>
        <span className="text-[9px] font-mono text-textSecondary/35 truncate hidden xl:inline">
          {en}
        </span>
      </div>
      <div className={`text-[22px] sm:text-[26px] font-mono font-semibold tabular-nums tracking-[-0.02em] leading-none ${c}`}>
        {value}
      </div>
      <div className={`mt-1.5 h-[13px] text-[11px] font-mono tabular-nums ${c} opacity-55`}>
        {sub ?? ''}
      </div>
    </div>
  );
};

// ── Main Component ──
export const PerformancePanel: React.FC<PerformancePanelProps> = ({
  metrics,
  equity,
  buyHold = [],
  trades = [],
  positionStatus = [],
  initialCapital,
  currency = 'USDT',
  onSelectTrade,
}) => {
  const [showBuyHold, setShowBuyHold] = useState(false);
  const [tab, setTab] = useState<TabId>('overview');

  const m = metrics as any;
  // 損益金額來源:後端沒有 net_profit 欄位,用 total_pnl(真實平倉盈虧)避免恆顯示 0 與%號不符。
  const netProfit = Number(m.total_pnl ?? (m.net_profit ?? 0));
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
  const avgWin = Number(m.avg_winner ?? m.avg_win ?? 0);
  const avgLoss = Number(m.avg_loser ?? m.avg_loss ?? 0);
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

  // ── TV Strategy Tester tabs ──
  const overviewRows: StatRow[] = [
    { label: '總損益', en: 'Net Profit', value: `${safeSigned(netProfit)} ${currency}`, sub: safePct(totalReturnPct), color: netProfit >= 0 ? 'pos' : 'neg', tip: '所有平倉交易盈虧總和（= 期末權益 − 初始資金）' },
    { label: '最大回撤', en: 'Max Drawdown', value: safeFmt(maxDdAmount), sub: safePct(maxDdPct, { signed: false }), color: 'neg', tip: '權益曲線從歷史峰值到谷值的最大跌幅' },
    { label: '總交易數', en: 'Total Trades', value: safeInt(totalTrades), sub: `${safeInt(winningTrades)}W/${safeInt(losingTrades)}L`, color: 'neutral', tip: '測試區間內產生的所有交易' },
    { label: '勝率', en: 'Percent Profitable', value: safePct(winRate, { signed: false }), color: winRate >= 50 ? 'pos' : 'neutral', tip: '獲利交易數 / 總交易數' },
    { label: '獲利因子', en: 'Profit Factor', value: fmtProfitFactor(profitFactor), color: profitFactor >= 1.5 ? 'pos' : profitFactor >= 1 ? 'neutral' : 'neg', tip: '總毛利 / 總毛損。>1 表示系統盈利' },
    { label: '夏普比率', en: 'Sharpe Ratio', value: safeFmt(sharpeRatio), color: sharpeRatio >= 1 ? 'pos' : sharpeRatio >= 0 ? 'neutral' : 'neg', tip: '超額報酬 / 報酬標準差。>1 為佳' },
    { label: '索提諾比率', en: 'Sortino Ratio', value: safeFmt(sortinoRatio), color: sortinoRatio >= 1 ? 'pos' : sortinoRatio >= 0 ? 'neutral' : 'neg', tip: '超額報酬 / 下行風險' },
    { label: '年化回報', en: 'Annual Return', value: safePct(annualReturnPct), color: annualReturnPct >= 0 ? 'pos' : 'neg', tip: '以測試區間天數年化（CAGR）' },
  ];

  const perfRows: StatRow[] = [
    { label: '年化回報', en: 'Annual Return', value: safePct(annualReturnPct), color: annualReturnPct >= 0 ? 'pos' : 'neg', tip: '以測試區間天數年化（CAGR）的複合年增率' },
    { label: '總回報', en: 'Total Return', value: safePct(totalReturnPct), color: totalReturnPct >= 0 ? 'pos' : 'neg', tip: '期末權益相對初始資金的總報酬率' },
    { label: '波動率', en: 'Volatility (ann.)', value: adv.annVol == null ? '—' : `${adv.annVol.toFixed(2)}%`, color: 'neutral', tip: '日報酬標準差年化（×√365）' },
    { label: '卡瑪比率', en: 'Calmar Ratio', value: safeFmt(calmar), color: calmar >= 1 ? 'pos' : calmar >= 0 ? 'neutral' : 'neg', tip: '年化回報 / 最大回撤' },
    { label: '恢復因子', en: 'Recovery Factor', value: fmtNum(adv.recoveryFactor), color: adv.recoveryFactor == null ? 'neutral' : adv.recoveryFactor >= 1 ? 'pos' : 'neg', tip: '期末權益 / 區間最低權益' },
    { label: '最大回撤期', en: 'Max DD Duration', value: safeInt(maxDdDuration || adv.maxDdBars), sub: '根K線', color: 'neutral', tip: '權益連續處於回撤狀態的最長 K 線數' },
    { label: '最大回撤天數', en: 'Max DD Days', value: `${adv.maxDdDays}`, sub: '天', color: 'neutral', tip: '資金曲線連續處於回撤狀態的最長天數' },
    { label: 'Rolling 30D Sharpe', en: '', value: fmtNum(ext.rollSharpe), color: ext.rollSharpe == null ? 'neutral' : ext.rollSharpe >= 1 ? 'pos' : ext.rollSharpe >= 0 ? 'neutral' : 'neg', tip: '以最近 30 根 K 線收益窗口計算的滾動夏普' },
    { label: '超額收益 α', en: 'Alpha', value: fmtPct(ext.alphaPct), color: ext.alphaPct == null ? 'neutral' : ext.alphaPct >= 0 ? 'pos' : 'neg', tip: '策略總回報 − 買進持有基準總回報' },
    { label: '相關性 β', en: 'Beta', value: fmtNum(ext.beta), sub: ext.corr == null ? undefined : `ρ=${ext.corr.toFixed(2)}`, color: ext.beta == null ? 'neutral' : ext.beta <= 0.5 ? 'pos' : ext.beta <= 1 ? 'neutral' : 'neg', tip: '策略收益對基準收益的敏感度' },
    { label: '超額夏普', en: 'Excess Sharpe', value: fmtNum(ext.exSharpe), color: ext.exSharpe == null ? 'neutral' : ext.exSharpe >= 0 ? 'pos' : 'neg', tip: '策略 Sharpe − 基準 Sharpe' },
    { label: '正報酬月比例', en: 'Positive Months', value: adv.posMonthPct == null ? '—' : `${adv.posMonthPct.toFixed(1)}%`, color: adv.posMonthPct == null ? 'neutral' : adv.posMonthPct >= 50 ? 'pos' : 'neg', tip: '正報酬月份佔所有有交易月份的比例' },
    { label: '最佳月份', en: 'Best Month', value: fmtPct(adv.bestMonth), color: 'pos', tip: '月度收益最高的一個月' },
    { label: '最差月份', en: 'Worst Month', value: fmtPct(adv.worstMonth), color: 'neg', tip: '月度收益最低的一個月' },
  ];

  const tradeRows: StatRow[] = [
    { label: '總交易數', en: 'Total Trades', value: safeInt(totalTrades), sub: `${safeInt(winningTrades)}W/${safeInt(losingTrades)}L`, color: 'neutral', tip: '測試區間內產生的所有交易' },
    { label: '勝率', en: 'Percent Profitable', value: safePct(winRate, { signed: false }), color: winRate >= 50 ? 'pos' : 'neutral', tip: '獲利交易數 / 總交易數' },
    { label: '期望值', en: 'Expectancy', value: safeSigned(expectancy), sub: '每筆', color: expectancy >= 0 ? 'pos' : 'neg', tip: '勝率×均盈 − 敗率×均虧' },
    { label: '盈虧比', en: 'Payoff Ratio', value: safeFmt(winLossRatio), color: winLossRatio >= 1.5 ? 'pos' : winLossRatio >= 1 ? 'neutral' : 'neg', tip: '平均盈利 / 平均虧損' },
    { label: '平均盈利', en: 'Avg Winning Trade', value: safeSigned(avgWin), color: 'pos', tip: '所有獲利交易的平均盈餘' },
    { label: '平均虧損', en: 'Avg Losing Trade', value: safeFmt(avgLoss), color: 'neg', tip: '所有虧損交易的平均虧損' },
    { label: '最大單筆盈利', en: 'Largest Win', value: safeSigned(largestWin), color: 'pos', tip: '單筆最大盈利金額' },
    { label: '最大單筆虧損', en: 'Largest Loss', value: safeFmt(largestLoss), color: 'neg', tip: '單筆最大虧損金額' },
    { label: '平均持倉', en: 'Avg Bars in Trades', value: safeFmt(avgHoldingBars, 1), sub: '根K線', color: 'neutral', tip: '每筆交易平均持有的 K 線數' },
    { label: '交易頻率', en: 'Trade Frequency', value: safeFmt(tradeFreq), sub: '筆/日', color: 'neutral', tip: '平均每天產生的交易筆數' },
    { label: '短期勝率', en: '<24 bars', value: adv.tfWinShort == null ? '—' : `${adv.tfWinShort.toFixed(1)}%`, color: adv.tfWinShort == null ? 'neutral' : adv.tfWinShort >= 50 ? 'pos' : 'neg', tip: '持有 <24 根 K 線的交易勝率' },
    { label: '中期勝率', en: '24-96 bars', value: adv.tfWinMid == null ? '—' : `${adv.tfWinMid.toFixed(1)}%`, color: adv.tfWinMid == null ? 'neutral' : adv.tfWinMid >= 50 ? 'pos' : 'neg', tip: '持有 24-96 根 K 線的交易勝率' },
    { label: '長期勝率', en: '>96 bars', value: adv.tfWinLong == null ? '—' : `${adv.tfWinLong.toFixed(1)}%`, color: adv.tfWinLong == null ? 'neutral' : adv.tfWinLong >= 50 ? 'pos' : 'neg', tip: '持有 >96 根 K 線的交易勝率' },
  ];

  const riskRows: StatRow[] = [
    { label: '最大回撤', en: 'Max Drawdown', value: safeFmt(maxDdAmount), sub: safePct(maxDdPct, { signed: false }), color: 'neg', tip: '權益曲線從歷史峰值到谷值的最大跌幅' },
    { label: 'VaR 95%', en: '', value: adv.var95 == null ? '—' : safePct(adv.var95 * 100), color: 'neg', tip: '每日收益 95% 置信度的歷史 VaR' },
    { label: 'CVaR 95%', en: 'Expected Shortfall', value: adv.cvar95 == null ? '—' : safePct(adv.cvar95 * 100), color: 'neg', tip: 'VaR 95% 條件下平均虧損（尾部期望）' },
    { label: 'VaR 99%', en: '', value: adv.var99 == null ? '—' : safePct(adv.var99 * 100), color: 'neg', tip: '每日收益 99% 置信度的歷史 VaR' },
    { label: 'CVaR 99%', en: 'Expected Shortfall', value: adv.cvar99 == null ? '—' : safePct(adv.cvar99 * 100), color: 'neg', tip: 'VaR 99% 條件下平均虧損（極端尾部）' },
    { label: '偏度', en: 'Skewness', value: fmtNum(adv.skew), color: adv.skew == null ? 'neutral' : adv.skew > 0 ? 'pos' : 'neg', tip: '正=右偏(偶有暴利)，負=左偏(偶有暴虧)' },
    { label: '峰度', en: 'Excess Kurtosis', value: fmtNum(adv.kurt), color: adv.kurt == null ? 'neutral' : adv.kurt > 0 ? 'neg' : 'pos', tip: '正=肥尾（極端風險高）' },
    { label: '波動率', en: 'Volatility (ann.)', value: adv.annVol == null ? '—' : `${adv.annVol.toFixed(2)}%`, color: 'neutral', tip: '日報酬標準差年化（×√365）' },
  ];

  const TABS: { id: TabId; label: string; en: string }[] = [
    { id: 'overview', label: '總覽', en: 'Overview' },
    { id: 'performance', label: '績效', en: 'Performance' },
    { id: 'trades', label: '交易分析', en: 'Trades Analysis' },
    { id: 'risk', label: '風險比率', en: 'Risk Ratios' },
  ];

  const activeRows =
    tab === 'overview' ? overviewRows
    : tab === 'performance' ? perfRows
    : tab === 'trades' ? tradeRows
    : riskRows;

  return (
    <div className="bg-surface">
      {/* ── Quality Score banner ── */}
      {m.quality_score != null && Number.isFinite(Number(m.quality_score)) && (
        <QualityScoreBanner
          score={Number(m.quality_score)}
          grade={String(m.quality_grade ?? 'F')}
          breakdown={m.quality_breakdown ?? {
            sharpe: 0, profit_factor: 0, win_rate: 0,
            drawdown: 0, sample: 0, raw_score: 0, confidence: 0,
            cap: 100, final_score: Number(m.quality_score) || 0,
            penalty_reason: null,
          }}
        />
      )}

      {/* ── Hero KPI strip (TV Strategy Tester top row) ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 border-b border-border/12">
        <HeroKpi
          label="總損益"
          en="Net Profit"
          value={safeSigned(netProfit)}
          sub={safePct(totalReturnPct)}
          color={netProfit >= 0 ? 'pos' : 'neg'}
          spark={<EquitySparkline data={equity} />}
        />
        <HeroKpi
          label="最大回撤"
          en="Max Drawdown"
          value={safeFmt(maxDdAmount)}
          sub={safePct(maxDdPct, { signed: false })}
          color="neg"
        />
        <HeroKpi
          label="總交易數"
          en="Total Trades"
          value={safeInt(totalTrades)}
          sub={`${safeInt(winningTrades)}W / ${safeInt(losingTrades)}L`}
          color="neutral"
        />
        <HeroKpi
          label="獲利因子"
          en="Profit Factor"
          value={fmtProfitFactor(profitFactor)}
          sub={`勝率 ${safePct(winRate, { signed: false })}`}
          color={profitFactor >= 1.5 ? 'pos' : profitFactor >= 1 ? 'neutral' : 'neg'}
        />
      </div>

      {/* ── Chart ── */}
      <EquityPnlChart
        equity={equity}
        buyHold={buyHold}
        trades={trades}
        initialCapital={initialCapital}
        showBuyHold={showBuyHold}
        currency={currency}
      />

      {/* ── Tab bar (TV Strategy Tester) ── */}
      <div className="flex items-stretch border-y border-border/12 bg-surface overflow-x-auto">
        {TABS.map((t) => {
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`relative px-4 sm:px-5 py-2.5 text-[12px] whitespace-nowrap transition-colors duration-150 ${
                active
                  ? 'text-text font-medium'
                  : 'text-textSecondary hover:text-text'
              }`}
            >
              <span>{t.label}</span>
              <span className="ml-1.5 text-[10px] font-mono text-textSecondary/40 hidden sm:inline">
                {t.en}
              </span>
              {active && (
                <span className="absolute inset-x-0 -bottom-px h-[2px] bg-accent" />
              )}
            </button>
          );
        })}
        <div className="flex-1 min-w-0" />
        <button
          type="button"
          onClick={() => setShowBuyHold((v) => !v)}
          className={`px-3 text-[10.5px] font-mono border-l border-border/12 transition-colors duration-150 ${
            showBuyHold ? 'text-accent' : 'text-textSecondary/60 hover:text-text'
          }`}
        >
          {showBuyHold ? '● B&H' : '○ B&H'}
        </button>
      </div>

      {/* ── Stat table ── */}
      <div className="px-4 sm:px-6 py-4">
        <StatTable rows={activeRows} cols={2} />
      </div>
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
  annVol: number | null;
  maxDdBars: number;
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
    maxDdDays: 0, annVol: null, maxDdBars: 0, recoveryFactor: null, skew: null, kurt: null,
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

  // 最大回撤持續天數 / 根數。後端 equity 不一定帶 drawdown 欄位，
  // 所以自己用 running peak 推導，避免整欄恆為 0。
  let maxDdDays = 0;
  let maxDdBars = 0;
  let curDays = 0;
  let curBars = 0;
  let prevT = 0;
  let peak = -Infinity;
  // 探測 timestamp 單位：秒 vs 毫秒
  const firstT = equity.length > 1 ? Number(equity[1].timestamp) || Number(equity[1].time) || 0 : 0;
  const isMs = firstT > 1e12;
  const daySec = isMs ? 86400000 : 86400;
  for (let i = 0; i < equity.length; i++) {
    const e = equity[i];
    const v = Number(e.equity) || 0;
    if (v > peak) peak = v;
    const rawDd = Number((e as any).drawdown);
    const dd = Number.isFinite(rawDd) && rawDd !== 0
      ? rawDd
      : peak > 0 ? (peak - v) / peak : 0;
    const t = Number(e.timestamp) || Number(e.time) || 0;
    if (dd > 0) {
      curBars += 1;
      if (prevT > 0 && t > prevT) {
        curDays += (t - prevT) / daySec;
      }
      // else: 首根回撤 bar 不重複計入
      maxDdDays = Math.max(maxDdDays, Math.round(curDays));
      maxDdBars = Math.max(maxDdBars, curBars);
    } else {
      curDays = 0;
      curBars = 0;
    }
    prevT = t;
  }

  // 年化波動率：後端 MetricsOut 沒有這欄，用日收益標準差 × √365 自行推導
  let annVol: number | null = null;
  if (n >= 2) {
    const mu = rets.reduce((a, b) => a + b, 0) / n;
    const varr = rets.reduce((a, b) => a + (b - mu) ** 2, 0) / (n - 1);
    annVol = Math.sqrt(varr) * Math.sqrt(365) * 100;
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
    tfWinShort, tfWinMid, tfWinLong, maxDdDays, annVol, maxDdBars, recoveryFactor,
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