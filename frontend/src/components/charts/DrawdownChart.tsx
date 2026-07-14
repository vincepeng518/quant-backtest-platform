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
      data
        .map((d) => {
          const raw = d.time ?? (d as any).timestamp;
          const t = typeof raw === 'string' ? Math.floor(new Date(raw).getTime() / 1000) : Math.floor((raw as number) / 1000);
          return { time: t as UTCTimestamp, value: -Math.abs(d.drawdown) };
        })
        .filter((d) => Number.isFinite(d.time) && d.time > 0)
    );

    chartRef.current = chart;

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
      chart.remove();
    };
  }, [data, theme]);

  return (
    <div className="relative w-full bg-surface p-4 border-t border-border/10">
      <div ref={containerRef} className="w-full h-[200px]" />
    </div>
  );
};
