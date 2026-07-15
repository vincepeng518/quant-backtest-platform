'use client';

import React, { useEffect, useRef } from 'react';
import { createChart, IChartApi, UTCTimestamp } from 'lightweight-charts';
import { EquityPoint } from '@/types/api';

interface DrawdownChartProps {
  data: EquityPoint[];
  theme?: 'light' | 'dark';
}

export const DrawdownChart: React.FC<DrawdownChartProps> = ({
  data,
  theme = 'dark',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const legendRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const isDark = theme === 'dark';

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 200,
      layout: {
        background: { color: isDark ? '#0a0a0a' : '#ffffff' },
        textColor: isDark ? '#a3a3a3' : '#525252',
      },
      grid: {
        vertLines: { color: isDark ? '#171717' : '#f5f5f5' },
        horzLines: { color: isDark ? '#171717' : '#f5f5f5' },
      },
      timeScale: {
        borderColor: isDark ? '#262626' : '#e5e5e5',
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: isDark ? '#262626' : '#e5e5e5',
      },
    });

    const drawdownArea = chart.addAreaSeries({
      topColor: 'rgba(239, 68, 68, 0.4)',
      bottomColor: 'rgba(239, 68, 68, 0.05)',
      lineColor: '#ef4444',
      lineWidth: 1,
      title: 'Drawdown (%)',
    });

    drawdownArea.setData(
      (() => {
        let peak = -Infinity;
        return data
          .map((d) => {
            const raw = d.time ?? (d as any).timestamp;
            const t = typeof raw === 'string' ? Math.floor(new Date(raw).getTime() / 1000) : Math.floor((raw as number) / 1000);
            const eq = (d as any).equity ?? 0;
            peak = Math.max(peak, eq);
            const dd = peak > 0 ? (eq - peak) / peak * 100 : 0;
            return { time: t as UTCTimestamp, value: -Math.abs(dd) };
          })
          .filter((d) => Number.isFinite(d.time) && d.time > 0);
      })()
    );

    chartRef.current = chart;

    // ── 懸停圖例 ──
    const legendEl = legendRef.current;
    const fmt = (n: number) => (n == null || isNaN(n) ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
    const renderLegend = (param: any) => {
      if (!legendEl || !param || !param.time || !param.seriesData) { if (legendEl) legendEl.style.display = 'none'; return; }
      const sd = param.seriesData.get(drawdownArea) as { value?: number } | undefined;
      const t = param.time as number;
      const dt = new Date(t * 1000).toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
      legendEl.style.display = 'flex';
      legendEl.replaceChildren();
      const mk = (txt: string, col: string) => { const s = document.createElement('span'); s.style.color = col; s.style.margin = '0 6px'; s.textContent = txt; return s; };
      legendEl.appendChild(mk(dt, '#a3a3a3'));
      legendEl.appendChild(mk(`回撤 ${fmt(sd?.value ?? NaN)}%`, '#ef4444'));
    };
    chart.subscribeCrosshairMove(renderLegend);

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
        });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.unsubscribeCrosshairMove(renderLegend);
      chart.remove();
    };
  }, [data, theme]);

  return (
    <div className="relative w-full bg-surface p-4 border-t border-border/10">
      <div
        ref={legendRef}
        className="pointer-events-none absolute left-6 top-6 z-10 hidden items-center font-mono text-xs"
        style={{ display: 'none' }}
      />
      <div ref={containerRef} className="w-full h-[200px]" />
    </div>
  );
};
