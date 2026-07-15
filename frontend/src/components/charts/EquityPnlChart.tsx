'use client';

import React, { useEffect, useRef } from 'react';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  UTCTimestamp,
  LineData,
  HistogramData,
} from 'lightweight-charts';
import { EquityPoint, TradeRecord } from '@/types/api';

interface EquityPnlChartProps {
  equity: EquityPoint[];
  buyHold?: EquityPoint[];
  trades?: TradeRecord[];
  initialCapital: number;
  showBuyHold: boolean;
  theme?: 'light' | 'dark';
}

const GREEN = '#10b981';
const RED = '#ef4444';
const BH_GRAY = '#a3a3a3';

// Parse entry_time / exit_time (number seconds OR ISO string) → unix seconds.
const toUnixSec = (v: any): number => {
  if (v == null) return 0;
  if (typeof v === 'number') return v;
  const ms = Date.parse(v);
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : 0;
};

const fmt = (n: number) =>
  n == null || isNaN(n) ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const EquityPnlChart: React.FC<EquityPnlChartProps> = ({
  equity,
  buyHold = [],
  trades = [],
  initialCapital,
  showBuyHold,
  theme = 'dark',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const legendRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  // Equity line + baseline are stable; rebuild when core data changes.
  useEffect(() => {
    if (!containerRef.current) return;

    const isDark = theme === 'dark';

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 420,
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
        vertLine: { color: isDark ? '#a3a3a3' : '#525252', width: 1, style: 2 },
        horzLine: { color: isDark ? '#a3a3a3' : '#525252', width: 1, style: 2 },
      },
      timeScale: {
        borderColor: isDark ? '#262626' : '#e5e5e5',
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: isDark ? '#262626' : '#e5e5e5',
      },
    });

    const eqData: LineData[] = equity
      .map((d) => ({ time: d.time as UTCTimestamp, value: d.equity }))
      .filter((d) => Number.isFinite(d.time) && d.time > 0);

    // Main equity line — green by default, with a horizontal baseline at
    // initial capital so the viewer can read positive/negative at a glance.
    const equityLine = chart.addLineSeries({
      color: GREEN,
      lineWidth: 2,
      title: '累計損益',
      priceLineVisible: false,
    });
    equityLine.setData(eqData);
    equityLine.createPriceLine({
      price: initialCapital,
      color: BH_GRAY,
      lineWidth: 1,
      lineStyle: 2, // dashed
      axisLabelVisible: true,
      title: '初始資金',
    });

    // Buy & Hold overlay (toggled by showBuyHold).
    let bhLine: ISeriesApi<'Line'> | null = null;
    if (showBuyHold && buyHold.length > 0) {
      bhLine = chart.addLineSeries({
        color: BH_GRAY,
        lineWidth: 1,
        title: '買進並持有',
        priceLineVisible: false,
      });
      bhLine.setData(
        buyHold
          .map((d) => ({ time: d.time as UTCTimestamp, value: d.equity }))
          .filter((d) => Number.isFinite(d.time) && d.time > 0)
      );
    }

    // Bottom histogram: one bar per trade at its exit_time, value = pnl.
    const histSeries = chart.addHistogramSeries({
      priceScaleId: 'pnl',
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
      title: '單筆盈虧',
    });
    histSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });
    const histData: HistogramData[] = trades
      .map((t) => {
        const pnl = Number(t.pnl) || 0;
        const t2 = toUnixSec(t.exit_time);
        return {
          time: t2 as UTCTimestamp,
          value: pnl,
          color: pnl >= 0 ? GREEN : RED,
        };
      })
      .filter((d) => Number.isFinite(d.time) && d.time > 0);
    histSeries.setData(histData);

    chartRef.current = chart;

    // ── Crosshair OHLC-style legend ──
    const legendEl = legendRef.current;
    const renderLegend = (param: any) => {
      if (!legendEl || !param || !param.time || !param.seriesData) {
        if (legendEl) legendEl.style.display = 'none';
        return;
      }
      const eq = param.seriesData.get(equityLine) as { value?: number } | undefined;
      const bh = showBuyHold && bhLine
        ? (param.seriesData.get(bhLine) as { value?: number } | undefined)
        : undefined;
      const hist = param.seriesData.get(histSeries) as { value?: number } | undefined;

      const t = param.time as number;
      const dt = new Date(t * 1000).toLocaleString('zh-TW', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hour12: false,
      });

      let html = `<span style="color:#a3a3a3;margin-right:8px">${dt}</span>`;
      if (eq) {
        const up = eq.value! >= initialCapital;
        const c = up ? GREEN : RED;
        html += `<span style="color:#a3a3a3">權益</span><span style="color:${c};margin:0 6px">${fmt(eq.value!)}</span>`;
      }
      if (bh) {
        html += `<span style="color:#a3a3a3">B&amp;H</span><span style="color:${BH_GRAY};margin:0 6px">${fmt(bh.value!)}</span>`;
      }
      if (hist) {
        const c = hist.value! >= 0 ? GREEN : RED;
        html += `<span style="color:#a3a3a3">單筆</span><span style="color:${c};margin:0 6px">${hist.value! >= 0 ? '+' : ''}${fmt(hist.value!)}</span>`;
      }
      legendEl.style.display = 'flex';
      legendEl.innerHTML = html;
    };
    chart.subscribeCrosshairMove(renderLegend);

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.unsubscribeCrosshairMove(renderLegend);
      chart.remove();
    };
  }, [equity, buyHold, trades, initialCapital, showBuyHold, theme]);

  return (
    <div className="relative w-full bg-surface">
      <div
        ref={legendRef}
        className="pointer-events-none absolute left-6 top-4 z-10 hidden items-center font-mono text-xs"
        style={{ display: 'none' }}
      />
      <div ref={containerRef} className="w-full h-[420px]" />
    </div>
  );
};
