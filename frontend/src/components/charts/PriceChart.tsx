'use client';

import React, { useEffect, useRef } from 'react';
import { createChart, IChartApi, ISeriesApi, UTCTimestamp, CandlestickData, CrosshairMode } from 'lightweight-charts';
import { ChartData, TradeMarker } from '@/types/chart';

interface PriceChartProps {
  data: ChartData[];
  markers?: TradeMarker[];
  theme?: 'light' | 'dark';
}

// ── 時間戳單位歧義 + NaN guard（與 TvBacktestChart 一致）──
const toTs = (raw: any): number => {
  if (raw == null || raw === '' || raw === undefined) return 0;
  let t: number;
  if (typeof raw === 'string') {
    const ms = new Date(raw).getTime();
    t = Number.isFinite(ms) ? ms / 1000 : NaN;
  } else {
    const n = Number(raw);
    if (!Number.isFinite(n)) return 0;
    t = n > 1e11 ? n / 1000 : n;
  }
  if (!Number.isFinite(t) || t <= 0) return 0;
  return Math.floor(t);
};

const fmt = (n: number, d = 2): string => {
  if (n == null || isNaN(n)) return '—';
  const abs = Math.abs(n);
  let digits = d;
  if (abs > 0 && abs < 0.01) digits = Math.max(d, 6);
  else if (abs >= 10000) digits = 0;
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
};

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
    const BG = isDark ? '#131722' : '#ffffff';
    const TXT = isDark ? '#d1d4dc' : '#131722';
    const GRID = isDark ? '#2a2e39' : '#e0e3eb';
    const BORDER = isDark ? '#363c4e' : '#e0e3eb';
    const CROSS = '#758696';
    const TV_UP = '#089981';
    const TV_DOWN = '#f23645';

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 450,
      layout: {
        background: { color: BG },
        textColor: TXT,
        fontSize: 11,
      },
      grid: {
        vertLines: { color: GRID },
        horzLines: { color: GRID },
      },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: CROSS, width: 1, style: 2 },
        horzLine: { color: CROSS, width: 1, style: 2 },
      },
      timeScale: {
        borderColor: BORDER,
        timeVisible: true,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
        rightOffset: 4,
        // @ts-ignore timezone supported in v4.1.x runtime
        timezone: 'Asia/Taipei',
      },
      rightPriceScale: {
        borderColor: BORDER,
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
    });

    const candlestickSeries = chart.addCandlestickSeries({
      upColor: TV_UP,
      downColor: TV_DOWN,
      borderUpColor: TV_UP,
      borderDownColor: TV_DOWN,
      wickUpColor: TV_UP,
      wickDownColor: TV_DOWN,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });

    const formattedData = data
      .filter((d) => d != null)
      .map((d) => {
        const t = toTs(d.time ?? (d as any).timestamp) as UTCTimestamp;
        if (t <= 0) return null as any;
        return {
          time: t,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
        };
      })
      .filter(Boolean);

    candlestickSeries.setData(formattedData);

    if (markers.length > 0) {
      const formattedMarkers = markers.map((m) => ({
        time: toTs(m.time) as UTCTimestamp,
        position: (m.position === 'belowBar' ? 'aboveBar' : 'belowBar') as 'aboveBar' | 'belowBar',
        color: m.color,
        shape: m.shape,
        text: m.text,
      }));
      candlestickSeries.setMarkers(formattedMarkers);
    }

    candlestickSeriesRef.current = candlestickSeries;
    chartRef.current = chart;

    // ── 懸停圖例 ──
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
      const color = up ? TV_UP : TV_DOWN;
      const t = param.time as number;
      const dt = new Date(t * 1000);
      const dateStr = dt.toLocaleString('zh-TW', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hour12: false,
      });
      legendEl.style.display = 'flex';
      legendEl.replaceChildren();
      const mk = (txt: string, col: string) => { const s = document.createElement('span'); s.style.color = col; s.style.margin = '0 6px'; s.style.fontSize = '11px'; s.textContent = txt; return s; };
      legendEl.appendChild(mk(dateStr, '#d1d4dc'));
      legendEl.appendChild(mk('O', '#787b86')); legendEl.appendChild(mk(fmt(bar.open), color));
      legendEl.appendChild(mk('H', '#787b86')); legendEl.appendChild(mk(fmt(bar.high), color));
      legendEl.appendChild(mk('L', '#787b86')); legendEl.appendChild(mk(fmt(bar.low), color));
      legendEl.appendChild(mk('C', '#787b86')); legendEl.appendChild(mk(fmt(bar.close), color));
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
    <div className="relative w-full bg-surface p-0 border-t border-[#363c4e]/20">
      <div
        ref={legendRef}
        className="pointer-events-none absolute left-6 top-4 z-10 hidden items-center font-mono text-xs tabular-nums"
        style={{ display: 'none' }}
      />
      <div ref={containerRef} className="w-full h-[450px]" />
    </div>
  );
};
