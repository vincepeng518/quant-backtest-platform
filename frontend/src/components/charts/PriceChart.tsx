'use client';

import React, { useEffect, useRef } from 'react';
import { createChart, IChartApi, ISeriesApi, UTCTimestamp } from 'lightweight-charts';
import { ChartData, TradeMarker } from '@/types/chart';

interface PriceChartProps {
  data: ChartData[];
  markers?: TradeMarker[];
  theme?: 'light' | 'dark';
}

export const PriceChart: React.FC<PriceChartProps> = ({
  data,
  markers = [],
  theme = 'dark',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const isDark = theme === 'dark';

    // Impeccable TradingView style configurations
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 450,
      layout: {
        background: { color: isDark ? '#0a0a0a' : '#ffffff' },
        textColor: isDark ? '#a3a3a3' : '#525252',
      },
      grid: {
        vertLines: { color: isDark ? '#171717' : '#f5f5f5' },
        horzLines: { color: isDark ? '#171717' : '#f5f5f5' },
      },
      crosshair: {
        mode: 1, // Magnet mode
        vertLine: {
          color: isDark ? '#a3a3a3' : '#525252',
          width: 0.5,
          style: 3, // dashed
        },
        horzLine: {
          color: isDark ? '#a3a3a3' : '#525252',
          width: 0.5,
          style: 3,
        },
      },
      timeScale: {
        borderColor: isDark ? '#262626' : '#e5e5e5',
        timeVisible: true,
        secondsVisible: false,
      },
      leftPriceScale: {
        visible: false,
      },
      rightPriceScale: {
        borderColor: isDark ? '#262626' : '#e5e5e5',
      },
    });

    const candlestickSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });

    const formattedData = data.map((d) => ({
      time: d.time as UTCTimestamp,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    candlestickSeries.setData(formattedData);

    // Apply markers if provided
    if (markers.length > 0) {
      const formattedMarkers = markers.map((m) => ({
        time: m.time as UTCTimestamp,
        position: m.position,
        color: m.color,
        shape: m.shape,
        text: m.text,
      }));
      candlestickSeries.setMarkers(formattedMarkers);
    }

    candlestickSeriesRef.current = candlestickSeries;
    chartRef.current = chart;

    // Handle Resize observer gracefully
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
  }, [data, markers, theme]);

  return (
    <div className="relative w-full bg-surface p-4 border-t border-border/10">
      <div ref={containerRef} className="w-full h-[450px]" />
    </div>
  );
};
