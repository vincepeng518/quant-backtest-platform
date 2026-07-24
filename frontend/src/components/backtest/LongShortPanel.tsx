'use client';

import React from 'react';
import type { PerformanceMetrics } from '@/types/api';

interface LongShortPanelProps {
  metrics: PerformanceMetrics;
}

const TV_UP = '#089981';
const TV_DOWN = '#f23645';
const NEUTRAL = '#d1d4dc';

const fmt = (n: number | undefined | null, d = 2): string => {
  if (n == null || isNaN(n)) return '—';
  const abs = Math.abs(n);
  if (abs >= 10000) return n.toLocaleString('en-US', { maximumFractionDigits: 0 });
  return n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
};

const pct = (n: number | undefined | null): string => {
  if (n == null || isNaN(n)) return '—';
  return `${(n * 100).toFixed(1)}%`;
};

const colorClass = (n: number | undefined | null): string => {
  if (n == null || isNaN(n)) return NEUTRAL;
  return n > 0 ? TV_UP : n < 0 ? TV_DOWN : NEUTRAL;
};

interface RowProps {
  label: string;
  long: number | undefined | null;
  short: number | undefined | null;
  format?: (n: number | undefined | null) => string;
  isPercent?: boolean;
}

const Row: React.FC<RowProps> = ({ label, long, short, format = fmt, isPercent = false }) => {
  const longColor = colorClass(typeof long === 'number' ? long : null);
  const shortColor = colorClass(typeof short === 'number' ? short : null);
  const fmtFn = isPercent ? pct : format;

  return (
    <tr className="border-b border-[#363c4e]/15">
      <td className="py-2 px-3 text-[10px] font-medium text-[#787b86] uppercase tracking-wider">
        {label}
      </td>
      <td className="py-2 px-3 text-sm font-mono font-semibold tabular-nums text-right" style={{ color: longColor }}>
        {fmtFn(long)}
      </td>
      <td className="py-2 px-3 text-sm font-mono font-semibold tabular-nums text-right" style={{ color: shortColor }}>
        {fmtFn(short)}
      </td>
    </tr>
  );
};

export const LongShortPanel: React.FC<LongShortPanelProps> = ({ metrics }) => {
  const hasData = (metrics.long_trades ?? 0) > 0 || (metrics.short_trades ?? 0) > 0;

  if (!hasData) {
    return (
      <div className="bg-[#161a25] rounded-sm border border-[#363c4e]/15 p-4 text-center text-sm text-[#787b86]">
        No long/short split data
      </div>
    );
  }

  return (
    <div className="bg-[#161a25] rounded-sm border border-[#363c4e]/15 overflow-hidden">
      {/* Header */}
      <div className="px-4 pt-3 pb-1 border-b border-[#363c4e]/15">
        <span className="text-[9px] font-semibold uppercase tracking-[0.12em] text-[#787b86]">
          Long / Short Breakdown
        </span>
      </div>

      {/* Summary bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-[#1e2233]">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-[#787b86]">Long</span>
          <span className="text-sm font-mono font-semibold" style={{ color: TV_UP }}>
            {metrics.long_trades ?? 0}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-[#787b86]">Short</span>
          <span className="text-sm font-mono font-semibold" style={{ color: TV_DOWN }}>
            {metrics.short_trades ?? 0}
          </span>
        </div>
      </div>

      {/* Table */}
      <table className="w-full">
        <thead>
          <tr className="border-b border-[#363c4e]/15">
            <th className="py-1.5 px-3 text-left text-[9px] font-semibold uppercase tracking-wider text-[#787b86]">Metric</th>
            <th className="py-1.5 px-3 text-right text-[9px] font-semibold uppercase tracking-wider" style={{ color: TV_UP }}>Long</th>
            <th className="py-1.5 px-3 text-right text-[9px] font-semibold uppercase tracking-wider" style={{ color: TV_DOWN }}>Short</th>
          </tr>
        </thead>
        <tbody>
          <Row label="Trades" long={metrics.long_trades} short={metrics.short_trades} format={(n) => n != null ? String(Math.round(n)) : '—'} />
          <Row label="Win Rate" long={metrics.long_win_rate} short={metrics.short_win_rate} isPercent />
          <Row label="Net PnL" long={metrics.long_pnl} short={metrics.short_pnl} />
          <Row label="Expectancy" long={metrics.long_expectancy} short={metrics.short_expectancy} />
          <Row label="Profit Factor" long={metrics.long_profit_factor} short={metrics.short_profit_factor} />
        </tbody>
      </table>
    </div>
  );
};
