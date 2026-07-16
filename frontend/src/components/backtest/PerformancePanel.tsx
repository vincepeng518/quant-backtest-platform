'use client';

import React, { useMemo, useState, useCallback } from 'react';
import { PerformanceMetrics, EquityPoint, TradeRecord, PositionStatusPoint } from '@/types/api';
import { EquityPnlChart } from '@/components/charts/EquityPnlChart';
import { Tooltip } from '@/components/ui/Tooltip';

// ── TV Color System ──
const TV_UP = '#089981';
const TV_DOWN = '#f23645';
const TV_NEUTRAL = '#787b86';
const TV_BG = '#131722';
const TV_SURFACE = '#161a25';
const TV_BORDER = '#363c4e';

// ── Safe formatting (handles Infinity, null, huge numbers) ──
const safeFmt = (n: number, decimals = 2): string => {
  if (n == null || !Number.isFinite(n)) return '∞';
  const abs = Math.abs(n);
  let d = decimals;
  if (abs >= 10000) d = 0;
  else if (abs >= 100) d = Math.max(d, 2);
  return n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
};
const safePct = (n: number): string => {
  if (n == null || !Number.isFinite(n)) return '—';
  // Backend may return 0–100 or 0–1 range. Heuristic: >1 means already pct*100
  const v = Math.abs(n) > 10 ? n : n * 100;
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
};
const safeSigned = (n: number, decimals = 2): string => {
  if (n == null || !Number.isFinite(n)) return '—';
  return `${n >= 0 ? '+' : ''}${safeFmt(n, decimals)}`;
};
const safeInt = (n: number): string => {
  if (n == null || !Number.isFinite(n)) return '∞';
  return Math.round(n).toLocaleString('en-US');
};

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
  const valueSize = mega ? 'text-2xl' : 'text-base';
  const subSize = mega ? 'text-xs' : 'text-[10px]';

  const inner = (
    <div
      className={`group relative bg-[#161a25] px-4 py-3 border-t border-[#363c4e]/20 flex flex-col gap-1 select-none card-lift cursor-default ${
        mega ? 'py-4' : ''
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-medium text-[#787b86] uppercase tracking-wider truncate">
          {label}
        </span>
        {sparkline && <div className="shrink-0">{sparkline}</div>}
      </div>
      <span className={`${valueSize} font-mono font-semibold tracking-tight ${colorClass}`}>
        {value}
      </span>
      {sub != null && (
        <span className={`${subSize} font-mono ${colorClass} opacity-70`}>{sub}</span>
      )}
      {/* Hover indicator line */}
      <div className="absolute inset-x-0 top-0 h-px bg-[#363c4e] opacity-0 group-hover:opacity-40 transition-opacity" />
    </div>
  );

  if (tip) {
    return <Tooltip content={tip} position="top">{inner}</Tooltip>;
  }
  return inner;
};

// ── Section Header ──
const SectionHeader: React.FC<{ title: string }> = ({ title }) => (
  <div className="col-span-full px-4 pt-4 pb-1">
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
    className={`px-2.5 py-1 rounded text-[10px] font-mono border transition-colors ${
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

  return (
    <div className="bg-[#161a25] border-t border-[#363c4e]/10">
      {/* ── Mega KPIs Row ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 border-b border-[#363c4e]/10">
        <KpiBlock
          label="總損益 Net Profit"
          value={`${safeSigned(netProfit)}`}
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
          value={safePct(maxDdPct)}
          sub={`${safeFmt(maxDdAmount)} USDT`}
          color="neg"
          mega
          tip="Max Drawdown：權益曲線從歷史峰值到谷值的最大跌幅"
        />
        <KpiBlock
          label="勝率 Win Rate"
          value={safePct(winRate)}
          sub={`${safeInt(winningTrades)}W / ${safeInt(losingTrades)}L`}
          color={winRate >= 50 ? 'pos' : 'neutral'}
          mega
          tip="Win Rate：獲利交易數 / 總交易數"
        />
      </div>

      {/* ── 回報類 (Returns) ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 border-b border-[#363c4e]/10">
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
          value={`${(volatility * 100).toFixed(2)}%`}
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
      <div className="grid grid-cols-2 sm:grid-cols-4 border-b border-[#363c4e]/10">
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
      <div className="grid grid-cols-2 sm:grid-cols-4 border-b border-[#363c4e]/10">
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