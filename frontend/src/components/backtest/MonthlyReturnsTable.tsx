'use client';

import React, { useMemo } from 'react';
import { EquityPoint } from '@/types/api';

interface MonthlyReturnsTableProps {
  equity: EquityPoint[];
  initialCapital: number;
}

// ── TV Color System ──
const TV_UP = '#089981';
const TV_DOWN = '#f23645';
const TV_NEUTRAL = '#787b86';

export const MonthlyReturnsTable: React.FC<MonthlyReturnsTableProps> = ({
  equity,
  initialCapital,
}) => {
  const rows = useMemo(() => {
    if (!equity || equity.length === 0) return [];
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
  const maxAbsRet = Math.max(...rows.map((r) => Math.abs(r.ret)), 1);

  // Heatmap intensity helper
  const heatBg = (ret: number): string => {
    const intensity = Math.min(Math.abs(ret) / maxAbsRet, 1);
    if (ret >= 0) {
      return `rgba(8,153,129,${(intensity * 0.15).toFixed(3)})`;
    }
    return `rgba(242,54,69,${(intensity * 0.15).toFixed(3)})`;
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm font-mono">
        <thead>
          <tr className="text-left text-xs uppercase text-[#787b86] border-b border-[#363c4e]/10">
            <th className="px-6 py-3 font-medium">月份</th>
            <th className="px-6 py-3 text-right font-medium">月度回報</th>
            <th className="px-6 py-3 text-right font-medium">月底權益</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.month}
              className="border-t border-[#363c4e]/10 hover:bg-white/[0.03] transition-colors"
            >
              <td className="px-6 py-2.5 text-[#787b86]">{r.month}</td>
              <td
                className="px-6 py-2.5 text-right font-semibold"
                style={{
                  color: r.ret >= 0 ? TV_UP : TV_DOWN,
                  backgroundColor: heatBg(r.ret),
                }}
              >
                {r.ret >= 0 ? '+' : ''}
                {r.ret.toFixed(2)}%
              </td>
              <td className="px-6 py-2.5 text-right text-[#d1d4dc]">
                {r.last.toLocaleString('en-US', {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </td>
            </tr>
          ))}
          {/* Summary row */}
          <tr className="border-t border-[#363c4e]/20 font-semibold">
            <td className="px-6 py-2.5 text-[#787b86]">
              平均 · 勝率 {positive}/{rows.length}
            </td>
            <td
              className="px-6 py-2.5 text-right"
              style={{ color: avg >= 0 ? TV_UP : TV_DOWN }}
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