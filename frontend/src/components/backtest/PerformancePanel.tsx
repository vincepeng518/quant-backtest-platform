'use client';

import React, { useMemo, useState } from 'react';
import { PerformanceMetrics, EquityPoint, TradeRecord, PositionStatusPoint } from '@/types/api';
import { EquityPnlChart } from '@/components/charts/EquityPnlChart';

interface PerformancePanelProps {
  metrics: PerformanceMetrics;
  equity: EquityPoint[];
  buyHold?: EquityPoint[];
  trades?: TradeRecord[];
  positionStatus?: PositionStatusPoint[];
  initialCapital: number;
}

const GREEN = '#10b981';
const RED = '#ef4444';

const toUnixSec = (v: any): number => {
  if (v == null) return 0;
  if (typeof v === 'number') return v;
  const ms = Date.parse(v);
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : 0;
};

const KpiBlock: React.FC<{
  label: string;
  value: string;
  sub?: string;
  color?: 'pos' | 'neg' | 'neutral' | 'inherit';
  tip?: string;
}> = ({ label, value, sub, color = 'inherit', tip }) => {
  const colorClass =
    color === 'pos'
      ? 'text-success'
      : color === 'neg'
      ? 'text-danger'
      : 'text-text';
  return (
    <div className="bg-surface px-4 py-4 border-t border-border/10 flex flex-col gap-1 select-none" title={tip}>
      <span className="text-[11px] font-medium text-textSecondary uppercase tracking-wider">
        {label}
      </span>
      <span className={`text-xl font-mono font-semibold tracking-tight ${colorClass}`}>
        {value}
      </span>
      {sub != null && (
        <span className={`text-xs font-mono ${colorClass}`}>{sub}</span>
      )}
    </div>
  );
};

const ToggleBtn: React.FC<{
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}> = ({ active, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    className={`px-2.5 py-1 rounded text-xs font-mono border transition-colors ${
      active
        ? 'border-accent/40 bg-accent/10 text-accent'
        : 'border-border/30 text-textSecondary hover:text-text'
    }`}
  >
    {children}
  </button>
);

export const PerformancePanel: React.FC<PerformancePanelProps> = ({
  metrics,
  equity,
  buyHold = [],
  trades = [],
  positionStatus = [],
  initialCapital,
}) => {
  const [showEquity, setShowEquity] = useState(true);
  const [showBuyHold, setShowBuyHold] = useState(false);
  const [showPnl, setShowPnl] = useState(true);
  const [showGainDd, setShowGainDd] = useState(true);
  const [showSpread, setShowSpread] = useState(false);

  const m = metrics as any;
  const netProfit = Number(m.net_profit ?? 0);
  const totalReturnPct = Number(m.total_return_pct ?? 0);
  const maxDdPct = Number(m.max_drawdown ?? 0);
  const maxDdAmount = (initialCapital * maxDdPct) / 100;
  const winRate = Number(m.win_rate ?? 0);
  const winningTrades = Number(m.winning_trades ?? 0);
  const totalTrades = Number(m.total_trades ?? 0);
  const profitFactor = Number(m.profit_factor ?? 0);
  const annualReturnPct = Number(m.annual_return_pct ?? 0);
  const calmar = Number(m.calmar_ratio ?? 0);
  const largestWin = Number(m.largest_win ?? 0);
  const largestLoss = Number(m.largest_loss ?? 0);
  const winLossRatio = Number(m.win_loss_ratio ?? 0);
  const expectancy = Number(m.expectancy ?? 0);
  const avgHoldingBars = Number(m.avg_holding_bars ?? 0);
  const tradeFreq = Number(m.trade_freq ?? 0);

  // ── Status bar segments (defensive: only when position_status exists) ──
  const statusSegments = useMemo(() => {
    if (!positionStatus || positionStatus.length === 0 || equity.length === 0) return [];
    const t0 = equity[0].time;
    const t1 = equity[equity.length - 1].time;
    const span = t1 - t0;
    if (span <= 0) return [];

    // Sort segments; each emits a block colored by its state, spanning to the
    // next segment's time (relative to the full equity range for X alignment).
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
        segs[i].state === 'long'
          ? GREEN
          : segs[i].state === 'short'
          ? RED
          : 'transparent';
      out.push({ left, width, color });
    }
    return out;
  }, [positionStatus, equity]);

  return (
    <div className="bg-surface border-t border-border/10">
      {/* 8 KPI blocks */}
      <div className="grid grid-cols-2 sm:grid-cols-4 border-border/10">
        <KpiBlock
          label="總損益"
          value={`${netProfit >= 0 ? '+' : ''}${netProfit.toFixed(2)} USDT`}
          sub={`${totalReturnPct >= 0 ? '+' : ''}${totalReturnPct.toFixed(2)}%`}
          color={netProfit >= 0 ? 'pos' : 'neg'}
          tip="Net Profit：所有平倉交易盈虧總和（= 期末權益 − 初始資金）"
        />
        <KpiBlock
          label="最大回撤"
          value={`${maxDdAmount.toFixed(2)} USDT`}
          sub={`${maxDdPct.toFixed(2)}%`}
          color="neg"
          tip="Max Drawdown：權益曲線從歷史峰值到谷值的最大跌幅"
        />
        <KpiBlock
          label="獲利交易"
          value={`${winRate.toFixed(2)}%`}
          sub={`${winningTrades}/${totalTrades}`}
          color="neutral"
          tip="Win Rate：獲利交易數 / 總交易數"
        />
        <KpiBlock
          label="獲利因子"
          value={`${profitFactor.toFixed(2)}`}
          color="neutral"
          tip="Profit Factor：總毛利 / 總毛損（絕對值）。>1 表示系統盈利"
        />
        <KpiBlock
          label="年化回報"
          value={`${annualReturnPct >= 0 ? '+' : ''}${annualReturnPct.toFixed(2)}%`}
          color={annualReturnPct >= 0 ? 'pos' : 'neg'}
          tip="Annualized Return：以測試區間天數年化（CAGR）的複合年增率"
        />
        <KpiBlock
          label="卡瑪比率"
          value={`${calmar.toFixed(2)}`}
          sub="年化/最大回撤"
          color="neutral"
          tip="Calmar Ratio：年化回報 / 最大回撤。越高代表回撤控制越好"
        />
        <KpiBlock
          label="最大單筆盈利"
          value={`${largestWin >= 0 ? '+' : ''}${largestWin.toFixed(2)}`}
          color="pos"
          tip="Largest Winning Trade：單筆最大盈利金額"
        />
        <KpiBlock
          label="最大單筆虧損"
          value={`${largestLoss.toFixed(2)}`}
          color="neg"
          tip="Largest Losing Trade：單筆最大虧損金額"
        />
        <KpiBlock
          label="盈虧比"
          value={`${winLossRatio.toFixed(2)}`}
          sub="均盈/均虧"
          color="neutral"
          tip="Payoff Ratio：平均盈利 / 平均虧損。>1 代表每虧 1 元能賺回更多"
        />
        <KpiBlock
          label="期望值"
          value={`${expectancy >= 0 ? '+' : ''}${expectancy.toFixed(2)}`}
          sub="每筆期望 PnL"
          color={expectancy >= 0 ? 'pos' : 'neg'}
          tip="Expectancy：勝率×均盈 − 敗率×均虧。單筆交易的平均期望盈虧"
        />
        <KpiBlock
          label="平均持倉"
          value={`${avgHoldingBars.toFixed(1)}`}
          sub="根/K線"
          color="neutral"
          tip="Avg Holding Period：每筆交易平均持有的 K 線數"
        />
        <KpiBlock
          label="交易頻率"
          value={`${tradeFreq.toFixed(2)}`}
          sub="筆/日"
          color="neutral"
          tip="Trade Frequency：測試區間內平均每天產生的交易筆數"
        />
      </div>

      {/* Legend / control panel (top-left overlay handled inside chart card) */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-t border-border/10">
        <ToggleBtn active={showEquity} onClick={() => setShowEquity((v) => !v)}>
          累計損益
        </ToggleBtn>
        <ToggleBtn active={showBuyHold} onClick={() => setShowBuyHold((v) => !v)}>
          {showBuyHold ? '👁' : '🚫'} 買進並持有
        </ToggleBtn>
        <ToggleBtn active={showPnl} onClick={() => setShowPnl((v) => !v)}>
          交易波動幅度
        </ToggleBtn>
        <ToggleBtn active={showGainDd} onClick={() => setShowGainDd((v) => !v)}>
          漲幅與回撤
        </ToggleBtn>
        <ToggleBtn active={showSpread} onClick={() => setShowSpread((v) => !v)}>
          {showSpread ? '📊' : '🚫'} 策略−基準
        </ToggleBtn>
      </div>

      {/* Status bar above X axis */}
      {statusSegments.length > 0 && (
        <div className="relative h-1.5 w-full bg-transparent px-0">
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
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Main chart */}
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
