'use client';

import React, { useEffect, useRef } from 'react';
import { createChart, IChartApi, UTCTimestamp } from 'lightweight-charts';
import { EquityPoint } from '@/types/api';

interface EquityCurveProps {
  data: EquityPoint[];
  buyHoldData?: EquityPoint[];
  theme?: 'light' | 'dark';
}

export const EquityCurve: React.FC<EquityCurveProps> = ({
  data,
  buyHoldData = [],
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
      height: 300,
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

    const strategyLine = chart.addLineSeries({
      color: '#3b82f6',
      lineWidth: 2,
      title: 'Strategy',
    });

    strategyLine.setData(
      data
        .map((d) => {
          const raw = d.time ?? (d as any).timestamp;
          const t = typeof raw === 'string' ? Math.floor(new Date(raw).getTime() / 1000) : Math.floor((raw as number) / 1000);
          return { time: t as UTCTimestamp, value: d.equity };
        })
        .filter((d) => Number.isFinite(d.time) && d.time > 0)
    );

    if (buyHoldData.length > 0) {
      const buyHoldLine = chart.addLineSeries({
        color: '#a3a3a3',
        lineWidth: 1,
        title: 'Buy & Hold',
      });
      buyHoldLine.setData(
        buyHoldData
          .map((d) => {
            const raw = d.time ?? (d as any).timestamp;
            const t = typeof raw === 'string' ? Math.floor(new Date(raw).getTime() / 1000) : Math.floor((raw as number) / 1000);
            return { time: t as UTCTimestamp, value: d.equity };
          })
          .filter((d) => Number.isFinite(d.time) && d.time > 0)
      );
    }

    chartRef.current = chart;

    // ── 悬停图例 ──
    const legendEl = legendRef.current;
    const fmt = (n: number) => (n == null || isNaN(n) ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
    const renderLegend = (param: any) => {
      if (!legendEl || !param || !param.time || !param.seriesData) { if (legendEl) legendEl.style.display = 'none'; return; }
      const sd = param.seriesData.get(strategyLine) as { value?: number } | undefined;
      const t = param.time as number;
      const dt = new Date(t * 1000).toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
      legendEl.style.display = 'flex';
      legendEl.innerHTML = `<span style="color:#a3a3a3;margin-right:8px">${dt}</span><span style="color:#3b82f6">权益 ${fmt(sd?.value ?? NaN)}</span>`;
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
  }, [data, buyHoldData, theme]);

  return (
    <div className="relative w-full bg-surface p-4 border-t border-border/10">
      <div
        ref={legendRef}
        className="pointer-events-none absolute left-6 top-6 z-10 hidden items-center font-mono text-xs"
        style={{ display: 'none' }}
      />
      <div ref={containerRef} className="w-full h-[300px]" />
    </div>
  );
};
