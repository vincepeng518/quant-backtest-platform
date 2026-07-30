'use client';

import React from 'react';
import { Tooltip } from '@/components/ui/Tooltip';

export interface StatRow {
  label: string;
  en?: string;
  value: string;
  sub?: string;
  color?: 'pos' | 'neg' | 'neutral';
  tip?: string;
}

/**
 * TradingView Strategy Tester 風格的統計表格。
 * 左側指標名，右側數值 — 不是卡片，是密集的資料列。
 */
export const StatTable: React.FC<{ rows: StatRow[]; cols?: 1 | 2 }> = ({ rows, cols = 2 }) => {
  const half = Math.ceil(rows.length / 2);
  const groups = cols === 2 ? [rows.slice(0, half), rows.slice(half)] : [rows];

  return (
    <div className={`grid gap-x-8 ${cols === 2 ? 'md:grid-cols-2' : 'grid-cols-1'}`}>
      {groups.map((group, gi) => (
        <div key={gi} className="divide-y divide-border/8">
          {group.map((r, i) => {
            const colorClass =
              r.color === 'pos'
                ? 'text-success'
                : r.color === 'neg'
                ? 'text-danger'
                : 'text-text';

            const row = (
              <div className="group flex items-baseline justify-between gap-4 py-[7px] px-1 -mx-1 rounded-sm hover:bg-text/[0.025] transition-colors duration-100">
                <div className="flex items-baseline gap-2 min-w-0">
                  <span className="text-[12.5px] text-textSecondary truncate leading-snug">
                    {r.label}
                  </span>
                  {r.en && (
                    <span className="text-[10px] text-textSecondary/40 font-mono truncate hidden lg:inline">
                      {r.en}
                    </span>
                  )}
                </div>
                <div className="flex items-baseline gap-2 shrink-0">
                  <span
                    className={`text-[13px] font-mono font-medium tabular-nums tracking-tight ${colorClass}`}
                  >
                    {r.value}
                  </span>
                  {r.sub && (
                    <span className="text-[10.5px] font-mono tabular-nums text-textSecondary/50 min-w-[52px] text-right">
                      {r.sub}
                    </span>
                  )}
                </div>
              </div>
            );

            return (
              <div key={i}>
                {r.tip ? (
                  <Tooltip content={r.tip} position="top">
                    {row}
                  </Tooltip>
                ) : (
                  row
                )}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
};

export default StatTable;
