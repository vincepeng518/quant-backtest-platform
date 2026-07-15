'use client';

import React, { useMemo } from 'react';
import { TradeRecord } from '@/types/api';

interface TradeStatsDistProps {
  trades: TradeRecord[];
}

const GREEN = '#10b981';
const RED = '#ef4444';

// 直方條組件：把值分到桶，渲染橫向/縱向條
const HistBars: React.FC<{
  buckets: { label: string; count: number; color: string }[];
  title: string;
}> = ({ buckets, title }) => {
  const max = Math.max(1, ...buckets.map((b) => b.count));
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-textSecondary">
        {title}
      </div>
      <div className="flex items-end gap-1.5 h-28">
        {buckets.map((b, i) => (
          <div key={i} className="flex flex-1 flex-col items-center justify-end gap-1">
            <span className="text-[10px] font-mono text-textSecondary">{b.count}</span>
            <div
              className="w-full rounded-t"
              style={{
                height: `${(b.count / max) * 100}%`,
                minHeight: 2,
                backgroundColor: b.color,
              }}
            />
            <span className="text-[9px] font-mono text-textSecondary whitespace-nowrap transform -rotate-45 origin-top-left">
              {b.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export const TradeStatsDist: React.FC<TradeStatsDistProps> = ({ trades }) => {
  const { pnlBuckets, holdBuckets, winCount, lossCount } = useMemo(() => {
    const wins = trades.filter((t) => (Number(t.pnl) || 0) >= 0);
    const losses = trades.filter((t) => (Number(t.pnl) || 0) < 0);

    // PnL 分桶（按金額區間）
    const pnlRanges = [
      { label: '<-500', test: (v: number) => v < -500, color: RED },
      { label: '-500~0', test: (v: number) => v >= -500 && v < 0, color: RED },
      { label: '0~500', test: (v: number) => v >= 0 && v < 500, color: GREEN },
      { label: '500~1k', test: (v: number) => v >= 500 && v < 1000, color: GREEN },
      { label: '>=1k', test: (v: number) => v >= 1000, color: GREEN },
    ];
    const pnlBuckets = pnlRanges.map((r) => ({
      label: r.label,
      color: r.color,
      count: trades.filter((t) => r.test(Number(t.pnl) || 0)).length,
    }));

    // 持倉時間分桶（K線數）
    const holdRanges = [
      { label: '1~5', test: (v: number) => v >= 1 && v <= 5 },
      { label: '6~10', test: (v: number) => v > 5 && v <= 10 },
      { label: '11~20', test: (v: number) => v > 10 && v <= 20 },
      { label: '21~50', test: (v: number) => v > 20 && v <= 50 },
      { label: '>50', test: (v: number) => v > 50 },
    ];
    const holdBuckets = holdRanges.map((r) => ({
      label: r.label,
      color: '#60a5fa',
      count: trades.filter((t) => r.test(Number(t.holding_bars) || 0)).length,
    }));

    return {
      pnlBuckets,
      holdBuckets,
      winCount: wins.length,
      lossCount: losses.length,
    };
  }, [trades]);

  if (!trades || trades.length === 0) return null;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <div>
        <div className="mb-3 flex items-center gap-4 text-xs font-mono">
          <span className="text-success">盈利 {winCount}</span>
          <span className="text-danger">虧損 {lossCount}</span>
        </div>
        <HistBars buckets={pnlBuckets} title="單筆盈虧分佈 (筆數)" />
      </div>
      <HistBars buckets={holdBuckets} title="持倉時間分佈 (K線)" />
    </div>
  );
};
