'use client';

import React, { useMemo } from 'react';
import type { TradeRecord } from '@/types/api';

interface MaeMfeScatterProps {
  trades: TradeRecord[];
  theme?: 'light' | 'dark';
}

const WIN = '#089981';
const LOSS = '#f23645';
const GRID = '#363a45';
const GRID_LIGHT = '#d1d4dc';
const TEXT = '#787b86';

const fmt = (n: number): string => {
  if (Math.abs(n) >= 1000) return n.toFixed(0);
  if (Math.abs(n) >= 1) return n.toFixed(2);
  return n.toFixed(4);
};

export const MaeMfeScatter: React.FC<MaeMfeScatterProps> = ({ trades, theme = 'dark' }) => {
  const valid = useMemo(
    () => trades.filter((t) => t.mae != null && t.mfe != null),
    [trades],
  );

  const { xMin, xMax, yMin, yMax } = useMemo(() => {
    if (valid.length === 0) return { xMin: -1, xMax: 1, yMin: -1, yMax: 1 };
    const mfeVals = valid.map((t) => t.mfe!);
    const maeVals = valid.map((t) => t.mae!);
    const xMin = Math.min(...mfeVals, 0);
    const xMax = Math.max(...mfeVals, 0);
    const yMin = Math.min(...maeVals, 0);
    const yMax = Math.max(...maeVals, 0);
    // add 10% padding
    const xPad = (xMax - xMin) * 0.1 || 1;
    const yPad = (yMax - yMin) * 0.1 || 1;
    return { xMin: xMin - xPad, xMax: xMax + xPad, yMin: yMin - yPad, yMax: yMax + yPad };
  }, [valid]);

  const W = 400;
  const H = 300;
  const PAD = { top: 20, right: 20, bottom: 40, left: 55 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const scaleX = (v: number) => PAD.left + ((v - xMin) / (xMax - xMin)) * plotW;
  const scaleY = (v: number) => PAD.top + ((yMax - v) / (yMax - yMin)) * plotH;

  const gridColor = theme === 'dark' ? GRID : GRID_LIGHT;
  const textColor = TEXT;

  if (valid.length === 0) {
    return (
      <div className="text-center text-sm py-8 opacity-50">
        No MAE/MFE data available
      </div>
    );
  }

  // quadrant counts
  const q = { ne: 0, nw: 0, se: 0, sw: 0 };
  valid.forEach((t) => {
    const mfe = t.mfe!, mae = t.mae!;
    if (mfe >= 0 && mae >= 0) q.ne++;
    else if (mfe < 0 && mae >= 0) q.nw++;
    else if (mfe >= 0 && mae < 0) q.se++;
    else q.sw++;
  });

  return (
    <div className="flex flex-col gap-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 300 }}>
        {/* grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
          const x = PAD.left + frac * plotW;
          const y = PAD.top + frac * plotH;
          return (
            <g key={frac}>
              <line x1={x} y1={PAD.top} x2={x} y2={PAD.top + plotH} stroke={gridColor} strokeWidth={0.5} />
              <line x1={PAD.left} y1={y} x2={PAD.left + plotW} y2={y} stroke={gridColor} strokeWidth={0.5} />
            </g>
          );
        })}
        {/* zero axes */}
        {xMin < 0 && xMax > 0 && (
          <line x1={scaleX(0)} y1={PAD.top} x2={scaleX(0)} y2={PAD.top + plotH} stroke={textColor} strokeWidth={1} strokeDasharray="4,2" />
        )}
        {yMin < 0 && yMax > 0 && (
          <line x1={PAD.left} y1={scaleY(0)} x2={PAD.left + plotW} y2={scaleY(0)} stroke={textColor} strokeWidth={1} strokeDasharray="4,2" />
        )}
        {/* axis labels */}
        <text x={PAD.left + plotW / 2} y={H - 4} textAnchor="middle" fill={textColor} fontSize={11}>
          MFE (favorable)
        </text>
        <text x={12} y={PAD.top + plotH / 2} textAnchor="middle" fill={textColor} fontSize={11} transform={`rotate(-90, 12, ${PAD.top + plotH / 2})`}>
          MAE (adverse)
        </text>
        {/* tick values */}
        <text x={PAD.left} y={PAD.top - 5} fill={textColor} fontSize={9}>{fmt(yMax)}</text>
        <text x={PAD.left} y={PAD.top + plotH + 12} fill={textColor} fontSize={9}>{fmt(yMin)}</text>
        <text x={PAD.left} y={PAD.top + plotH + 12} fill={textColor} fontSize={9} textAnchor="start">{fmt(xMin)}</text>
        <text x={PAD.left + plotW} y={PAD.top + plotH + 12} fill={textColor} fontSize={9} textAnchor="end">{fmt(xMax)}</text>
        {/* dots */}
        {valid.map((t, i) => {
          const isWin = (t.pnl ?? 0) >= 0;
          return (
            <circle
              key={i}
              cx={scaleX(t.mfe!)}
              cy={scaleY(t.mae!)}
              r={3}
              fill={isWin ? WIN : LOSS}
              opacity={0.7}
            >
              <title>
                {`PnL: ${fmt(t.pnl ?? 0)}\nMFE: ${fmt(t.mfe!)}\nMAE: ${fmt(t.mae!)}`}
              </title>
            </circle>
          );
        })}
      </svg>
      {/* legend / quadrant summary */}
      <div className="flex justify-between text-xs opacity-70 px-2">
        <span>Trades: {valid.length}</span>
        <span style={{ color: WIN }}>● Win</span>
        <span style={{ color: LOSS }}>● Loss</span>
      </div>
    </div>
  );
};
