'use client';

import React, { useEffect, useRef, useState } from 'react';
import { createChart, IChartApi, UTCTimestamp, CrosshairMode } from 'lightweight-charts';
import { EquityPoint } from '@/types/api';

interface DrawdownChartProps {
  data: EquityPoint[];
  theme?: 'light' | 'dark';
}

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

// ── defensive: 排序 + 去重 (lightweight-charts 要求 asc 唯一 time) ──
const sortDedupe = <T extends Record<string, any>>(arr: T[]): T[] => {
  const seen = new Set<number>();
  return [...(arr || [])]
    .sort((a, b) => toTs(a.time ?? (a as any).timestamp) - toTs(b.time ?? (a as any).timestamp))
    .filter((d) => {
      const t = toTs(d.time ?? (d as any).timestamp);
      if (t <= 0 || seen.has(t)) return false;
      seen.add(t);
      return true;
    });
};

const fmt = (n: number, d = 2): string => {
  if (n == null || isNaN(n)) return '—';
  const abs = Math.abs(n);
  if (abs >= 10000) return n.toLocaleString('en-US', { maximumFractionDigits: 0 });
  return n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
};

export const DrawdownChart: React.FC<DrawdownChartProps> = ({
  data,
  theme = 'dark',
}) => {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const legendRef = useRef<HTMLDivElement>(null);

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
      height: 200,
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
        fixLeftEdge: true,
        fixRightEdge: true,
        // @ts-ignore timezone supported in v4.1.x runtime
        timezone: 'Asia/Taipei',
      },
      rightPriceScale: { borderColor: BORDER, scaleMargins: { top: 0.1, bottom: 0.1 } },
    });

    const drawdownArea = chart.addAreaSeries({
      topColor: 'rgba(242, 54, 69, 0.4)',
      bottomColor: 'rgba(242, 54, 69, 0.05)',
      lineColor: '#f23645',
      lineWidth: 1,
      title: 'Drawdown (%)',
    });

    const ddData = (() => {
      let peak = -Infinity;
      return sortDedupe(data)
        .map((d) => {
          const t = toTs(d.time ?? (d as any).timestamp) as UTCTimestamp;
          if (t <= 0) return null as any;
          const eq = (d as any).equity ?? 0;
          peak = Math.max(peak, eq);
          const dd = peak > 0 ? (eq - peak) / peak * 100 : 0;
          return { time: t, value: -Math.abs(dd) };
        })
        .filter(Boolean);
    })();
    if (ddData.length > 0) drawdownArea.setData(ddData);

    chartRef.current = chart;

    const legendEl = legendRef.current;
    const renderLegend = (param: any) => {
      if (!legendEl || !param || !param.time || !param.seriesData) { if (legendEl) legendEl.style.display = 'none'; return; }
      const sd = param.seriesData.get(drawdownArea) as { value?: number } | undefined;
      const t = param.time as number;
      const dt = new Date(t * 1000).toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
      legendEl.style.display = 'flex';
      legendEl.replaceChildren();
      const mk = (txt: string, col: string) => { const s = document.createElement('span'); s.style.color = col; s.style.margin = '0 6px'; s.style.fontSize = '11px'; s.textContent = txt; return s; };
      legendEl.appendChild(mk(dt, '#d1d4dc'));
      legendEl.appendChild(mk(`回撤 ${fmt(sd?.value ?? NaN)}%`, '#f23645'));
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
  }, [data, theme]);

  const toggleFullscreen = () => {
    const el = containerRef.current?.parentElement;
    if (!el) return;
    if (!isFullscreen) el.requestFullscreen?.().catch(() => {});
    else document.exitFullscreen?.().catch(() => {});
    setIsFullscreen((v) => !v);
  };

  return (
    <div className="relative w-full bg-surface p-0 border-t border-[#363c4e]/20">
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
      <div ref={containerRef} className="w-full h-[200px]" />
    </div>
  );
};
