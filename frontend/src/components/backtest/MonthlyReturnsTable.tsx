'use client';

import React, { useMemo } from 'react';
import { EquityPoint, TradeRecord } from '@/types/api';

interface MonthlyReturnsTableProps {
  equity: EquityPoint[];
  initialCapital: number;
}

const GREEN = '#10b981';
const RED = '#ef4444';

export const MonthlyReturnsTable: React.FC<MonthlyReturnsTableProps> = ({
  equity,
  initialCapital,
}) => {
  const rows = useMemo(() => {
    if (!equity || equity.length === 0) return [];
    // 按自然月分組，計算每月月底權益相對上月月底的回報%
    const byMonth = new Map<string, { first: number; last: number }>();
    for (const p of equity) {
      const d = new Date((p.time as number) * 1000);
      const key = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
      const eq = p.equity;
      if (!byMonth.has(key)) byMonth.set(key, { first: eq, last: eq });
      byMonth.get(key)!.last = eq;
    }
    const keys = Array.from(byMonth.keys()).sort();
    let prevLast = initialCapital;
    return keys.map((k) => {
      const { first, last } = byMonth.get(k)!;
      const ret = ((last - prevLast) / (prevLast || 1)) * 100;
      prevLast = last;
      return { month: k, ret, last };
    });
  }, [equity, initialCapital]);

  if (rows.length === 0) return null;

  const avg = rows.reduce((s, r) => s + r.ret, 0) / rows.length;
  const positive = rows.filter((r) => r.ret >= 0).length;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm font-mono">
        <thead>
          <tr className="text-left text-xs uppercase text-textSecondary border-b border-border/10">
            <th className="px-6 py-3">月份</th>
            <th className="px-6 py-3 text-right">月度回報</th>
            <th className="px-6 py-3 text-right">月底權益</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.month} className="border-t border-border/10 hover:bg-white/[0.02]">
              <td className="px-6 py-2.5 text-textSecondary">{r.month}</td>
              <td
                className="px-6 py-2.5 text-right font-semibold"
                style={{ color: r.ret >= 0 ? GREEN : RED }}
              >
                {r.ret >= 0 ? '+' : ''}
                {r.ret.toFixed(2)}%
              </td>
              <td className="px-6 py-2.5 text-right text-text">
                {r.last.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </td>
            </tr>
          ))}
          <tr className="border-t border-border/20 font-semibold">
            <td className="px-6 py-2.5 text-textSecondary">
              平均 / 勝率 {positive}/{rows.length}
            </td>
            <td
              className="px-6 py-2.5 text-right"
              style={{ color: avg >= 0 ? GREEN : RED }}
            >
              {avg >= 0 ? '+' : ''}
              {avg.toFixed(2)}%
            </td>
            <td className="px-6 py-2.5" />
          </tr>
        </tbody>
      </table>
    </div>
  );
};
