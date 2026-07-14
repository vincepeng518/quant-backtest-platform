'use client';

import React, { useEffect, useRef } from 'react';
import { createChart, IChartApi, ISeriesApi, UTCTimestamp, CandlestickData, Time } from 'lightweight-charts';
import { ChartData, TradeMarker } from '@/types/chart';

interface PriceChartProps {
  data: ChartData[];
  markers?: TradeMarker[];
  theme?: 'light' | 'dark';
}

const fmt = (n: number) => (n == null || isNaN(n) ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

export const PriceChart: React.FC<PriceChartProps> = ({
  data,
  markers = [],
  theme = 'dark',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const legendRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const isDark = theme === 'dark';

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
          width: 1,
          style: 2, // dashed
        },
        horzLine: {
          color: isDark ? '#a3a3a3' : '#525252',
          width: 1,
          style: 2,
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

    const formattedData = data
      .filter((d) => d != null)
      .map((d) => {
        const raw = d.time ?? (d as any).timestamp;
        const t =
          typeof raw === 'string'
            ? Math.floor(new Date(raw).getTime() / 1000)
            : Math.floor((raw as number) / 1000);
        return {
          time: t as UTCTimestamp,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
        };
      })
      .filter((d) => Number.isFinite(d.time) && d.time > 0);

    candlestickSeries.setData(formattedData);

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

    // ── 悬停图例 (Crosshair OHLC legend) ──
    const legendEl = legendRef.current;
    const renderLegend = (param: any) => {
      if (!legendEl) return;
      if (!param || !param.time || !param.seriesData) {
        legendEl.style.display = 'none';
        return;
      }
      const bar = param.seriesData.get(candlestickSeries) as CandlestickData | undefined;
      if (!bar) {
        legendEl.style.display = 'none';
        return;
      }
      const up = (bar.close ?? 0) >= (bar.open ?? 0);
      const color = up ? '#10b981' : '#ef4444';
      const t = param.time as number;
      const dt = new Date(t * 1000);
      const dateStr = dt.toLocaleString('zh-TW', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hour12: false,
      });
      legendEl.style.display = 'flex';
      legendEl.innerHTML =
        `<span style="color:#a3a3a3;margin-right:8px">${dateStr}</span>` +
        `<span style="color:#a3a3a3">O</span><span style="color:${color};margin:0 6px">${fmt(bar.open)}</span>` +
        `<span style="color:#a3a3a3">H</span><span style="color:${color};margin:0 6px">${fmt(bar.high)}</span>` +
        `<span style="color:#a3a3a3">L</span><span style="color:${color};margin:0 6px">${fmt(bar.low)}</span>` +
        `<span style="color:#a3a3a3">C</span><span style="color:${color};margin:0 6px">${fmt(bar.close)}</span>`;
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
  }, [data, markers, theme]);

  return (
    <div className="relative w-full bg-surface p-4 border-t border-border/10">
      <div
        ref={legendRef}
        className="pointer-events-none absolute left-6 top-6 z-10 hidden items-center font-mono text-xs"
        style={{ display: 'none' }}
      />
      <div ref={containerRef} className="w-full h-[450px]" />
    </div>
  );
};
