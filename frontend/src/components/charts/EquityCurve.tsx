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
      data.map((d) => ({
        time: d.time as UTCTimestamp,
        value: d.equity,
      }))
    );

    if (buyHoldData.length > 0) {
      const buyHoldLine = chart.addLineSeries({
        color: '#a3a3a3',
        lineWidth: 1.5,
        title: 'Buy & Hold',
      });
      buyHoldLine.setData(
        buyHoldData.map((d) => ({
          time: d.time as UTCTimestamp,
          value: d.equity,
        }))
      );
    }

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
  }, [data, buyHoldData, theme]);

  return (
    <div className="relative w-full bg-surface p-4 border-t border-border/10">
      <div ref={containerRef} className="w-full h-[300px]" />
    </div>
  );
};
