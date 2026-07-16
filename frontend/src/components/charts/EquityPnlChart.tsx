'use client';

import React, { useEffect, useRef, useState } from 'react';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  UTCTimestamp,
  LineData,
  HistogramData,
  CrosshairMode,
} from 'lightweight-charts';
import { EquityPoint, TradeRecord } from '@/types/api';

interface EquityPnlChartProps {
  equity: EquityPoint[];
  buyHold?: EquityPoint[];
  trades?: TradeRecord[];
  initialCapital: number;
  showBuyHold: boolean;
  showSpread?: boolean;
  theme?: 'light' | 'dark';
}

const STRATEGY = '#2962FF';
const TV_UP = '#089981';
const TV_DOWN = '#f23645';
const BH_GRAY = '#787b86';

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
  if (abs > 0 && abs < 0.01) return n.toLocaleString('en-US', { minimumFractionDigits: 6, maximumFractionDigits: 6 });
  if (abs >= 10000) return n.toLocaleString('en-US', { maximumFractionDigits: 0 });
  return n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
};

// Parse entry_time / exit_time (number seconds OR ISO string) → unix seconds.
const toUnixSec = (v: any): number => {
  if (v == null) return 0;
  if (typeof v === 'number') return v;
  const ms = Date.parse(v);
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : 0;
};

export const EquityPnlChart: React.FC<EquityPnlChartProps> = ({
  equity,
  buyHold = [],
  trades = [],
  initialCapital,
  showBuyHold,
  showSpread = false,
  theme = 'dark',
}) => {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const legendRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const isDark = theme === 'dark';
    const BG = isDark ? '#131722' : '#ffffff';
    const TXT = isDark ? '#d1d4dc' : '#131722';
    const GRID = isDark ? '#2a2e39' : '#e0e3eb';
    const BORDER = isDark ? '#363c4e' : '#e0e3eb';
    const CROSS = '#758696';

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 420,
      layout: { background: { color: BG }, textColor: TXT, fontSize: 11 },
      grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
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
        // @ts-ignore timezone supported in v4.1.x runtime
        timezone: 'Asia/Taipei',
      },
      rightPriceScale: { borderColor: BORDER, scaleMargins: { top: 0.1, bottom: 0.1 } },
    });

    const eqData: LineData[] = equity
      .map((d) => ({ time: toTs(d.time ?? (d as any).timestamp) as UTCTimestamp, value: d.equity }))
      .filter((d) => d.time > 0);

    const equityLine = chart.addLineSeries({
      color: STRATEGY,
      lineWidth: 2,
      title: '累計損益',
      priceLineVisible: false,
    });
    equityLine.setData(eqData);
    equityLine.createPriceLine({
      price: initialCapital,
      color: BH_GRAY,
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: '初始資金',
    });

    let peakVal = -Infinity;
    let peakIdx = -1;
    let maxDd = 0;
    let troughIdx = -1;
    const eqVals = equity.map((d) => d.equity);
    const runningPeak: number[] = [];
    for (let i = 0; i < eqVals.length; i++) {
      if (eqVals[i] > peakVal) {
        peakVal = eqVals[i];
        peakIdx = i;
      }
      runningPeak.push(peakVal);
      const dd = (peakVal - eqVals[i]) / (peakVal || 1);
      if (dd > maxDd) {
        maxDd = dd;
        troughIdx = i;
      }
    }
    const markers: any[] = [];
    if (peakIdx >= 0 && eqData[peakIdx]) {
      markers.push({
        time: eqData[peakIdx].time,
        position: 'aboveBar',
        color: TV_UP,
        shape: 'circle',
        text: '峰值',
      });
    }
    if (troughIdx >= 0 && eqData[troughIdx]) {
      markers.push({
        time: eqData[troughIdx].time,
        position: 'belowBar',
        color: TV_DOWN,
        shape: 'circle',
        text: `最大回撤 ${((maxDd) * 100).toFixed(1)}%`,
      });
    }
    if (markers.length > 0) equityLine.setMarkers(markers);

    let spreadLine: ISeriesApi<'Line'> | null = null;
    if (showSpread && buyHold.length > 0) {
      const bhMap = new Map<number, number>(
        buyHold.map((d) => [toTs(d.time ?? (d as any).timestamp) as number, d.equity])
      );
      const spreadData: LineData[] = eqData
        .map((d) => {
          const bh = bhMap.get(d.time as number);
          return bh != null ? { time: d.time, value: d.value - bh } : null;
        })
        .filter((d): d is LineData => d != null);
      if (spreadData.length > 0) {
        spreadLine = chart.addLineSeries({
          color: '#f59e0b',
          lineWidth: 1,
          title: '策略−基準',
          priceLineVisible: false,
          priceScaleId: 'spread',
        });
        spreadLine.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0.6 } });
        spreadLine.setData(spreadData);
        spreadLine.createPriceLine({
          price: 0,
          color: BH_GRAY,
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: false,
          title: '',
        });
      }
    }

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
          .map((d) => ({ time: toTs(d.time ?? (d as any).timestamp) as UTCTimestamp, value: d.equity }))
          .filter((d) => d.time > 0)
      );
    }

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
          color: pnl >= 0 ? 'rgba(8,153,129,0.5)' : 'rgba(242,54,69,0.5)',
        };
      })
      .filter((d) => Number.isFinite(d.time) && d.time > 0);
    histSeries.setData(histData);

    // ── series visibility toggle with fade ──
    const applyVisibility = (s: any, visible: boolean) => {
      s.applyOptions({ visible });
      const el = (s as any)._legendEls;
      if (el) el.forEach((e: HTMLElement) => { e.style.opacity = visible ? '1' : '0.3'; e.style.transition = 'opacity 200ms'; });
    };
    // (simple fade handled by toggle buttons in UI below)
    chartRef.current = chart;

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

      legendEl.style.display = 'flex';
      legendEl.replaceChildren();
      const mk = (txt: string, col: string, gap = '0 6px') => { const s = document.createElement('span'); s.style.color = col; s.style.margin = gap; s.style.fontSize = '11px'; s.textContent = txt; return s; };
      legendEl.appendChild(mk(dt, '#d1d4dc', '0 8px 0 0'));
      if (eq) {
        const up = eq.value! >= initialCapital;
        const c = up ? TV_UP : TV_DOWN;
        legendEl.appendChild(mk('權益', '#787b86'));
        legendEl.appendChild(mk(fmt(eq.value!), c));
      }
      if (bh) {
        legendEl.appendChild(mk('B&H', '#787b86'));
        legendEl.appendChild(mk(fmt(bh.value!), BH_GRAY));
      }
      if (hist) {
        const c = hist.value! >= 0 ? TV_UP : TV_DOWN;
        legendEl.appendChild(mk('單筆', '#787b86'));
        legendEl.appendChild(mk(`${hist.value! >= 0 ? '+' : ''}${fmt(hist.value!)}`, c));
      }
      if (showSpread && spreadLine) {
        const sp = param.seriesData.get(spreadLine) as { value?: number } | undefined;
        if (sp) {
          const c = sp.value! >= 0 ? TV_UP : TV_DOWN;
          legendEl.appendChild(mk('差值', '#787b86'));
          legendEl.appendChild(mk(`${sp.value! >= 0 ? '+' : ''}${fmt(sp.value!)}`, c));
        }
      }
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
  }, [equity, buyHold, trades, initialCapital, showBuyHold, showSpread, theme]);

  const toggleFullscreen = () => {
    const el = containerRef.current?.parentElement;
    if (!el) return;
    if (!isFullscreen) {
      el.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
    setIsFullscreen((v) => !v);
  };

  return (
    <div className="relative w-full bg-surface">
      <button
        type="button"
        onClick={toggleFullscreen}
        className="absolute right-3 top-3 z-20 rounded bg-[#161a25]/80 px-2 py-1 text-[10px] font-mono text-[#787b86] transition-colors duration-150 hover:text-[#d1d4dc] active:scale-[0.97]"
      >
        {isFullscreen ? '退出' : '⛶'}
      </button>
      <div
        ref={legendRef}
        className="pointer-events-none absolute left-6 top-4 z-10 hidden items-center font-mono text-xs tabular-nums"
        style={{ display: 'none' }}
      />
      <div ref={containerRef} className="w-full h-[420px]" />
    </div>
  );
};
