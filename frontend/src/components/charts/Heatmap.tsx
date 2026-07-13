'use client';

import React, { useState } from 'react';
import type { OptimizeGrid } from '@/types/api';

interface HeatmapProps {
  grid: OptimizeGrid;
}

export const Heatmap: React.FC<HeatmapProps> = ({ grid }) => {
  const [hover, setHover] = useState<{ x: number; y: number; v: number | null } | null>(null);
  const { param_x, param_y, x_values, y_values, scores } = grid;

  const flat = scores.flat().filter((v): v is number => v !== null);
  const min = flat.length ? Math.min(...flat) : 0;
  const max = flat.length ? Math.max(...flat) : 1;
  const span = max - min || 1;

  const colorFor = (v: number | null) => {
    if (v === null) return 'rgba(255,255,255,0.04)';
    const t = (v - min) / span;
    if (t < 0.5) {
      const k = t / 0.5;
      return `rgba(${Math.round(220 + k * 35)}, ${Math.round(70 + k * 120)}, ${Math.round(70 + k * 60)}, 0.85)`;
    }
    const k = (t - 0.5) / 0.5;
    return `rgba(${Math.round(80 - k * 40)}, ${Math.round(200 + k * 30)}, ${Math.round(120 - k * 40)}, 0.85)`;
  };

  const cell = 38;
  const labelW = 56;
  const labelH = 28;
  const w = labelW + x_values.length * cell;
  const h = labelH + y_values.length * cell;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs font-mono text-textSecondary">
        <span>{param_x} (x) × {param_y} (y)</span>
        <span>{min.toFixed(2)} → {max.toFixed(2)}</span>
      </div>
      <svg width={w} height={h} className="max-w-full">
        {y_values.map((yv, yi) =>
          x_values.map((xv, xi) => {
            const v = scores[yi]?.[xi] ?? null;
            return (
              <rect
                key={`${xi}-${yi}`}
                x={labelW + xi * cell}
                y={labelH + yi * cell}
                width={cell - 2}
                height={cell - 2}
                rx={3}
                fill={colorFor(v)}
                onMouseEnter={() => setHover({ x: xi, y: yi, v })}
                onMouseLeave={() => setHover(null)}
                className="cursor-pointer transition-opacity hover:opacity-80"
              />
            );
          })
        )}
        {x_values.map((xv, xi) => (
          <text key={`xl-${xi}`} x={labelW + xi * cell + cell / 2} y={labelH - 8} textAnchor="middle" className="fill-textSecondary" fontSize={10}>
            {xv}
          </text>
        ))}
        {y_values.map((yv, yi) => (
          <text key={`yl-${yi}`} x={labelW - 6} y={labelH + yi * cell + cell / 2 + 3} textAnchor="end" className="fill-textSecondary" fontSize={10}>
            {yv}
          </text>
        ))}
      </svg>
      {hover && (
        <div className="text-xs font-mono text-textSecondary">
          {param_x}={x_values[hover.x]}, {param_y}={y_values[hover.y]} →{' '}
          <span className={hover.v !== null && hover.v >= 0 ? 'text-success' : 'text-danger'}>
            {hover.v === null ? 'n/a' : hover.v.toFixed(3)}
          </span>
        </div>
      )}
    </div>
  );
};
