'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { init, dispose, Chart, KLineData, LineType, CandleType, YAxisPosition, YAxisType } from 'klinecharts';
import type { ChartData, TradeMarker } from '@/types/chart';
import type { EquityPoint } from '@/types/api';

interface TvBacktestChartProps {
  data: ChartData[];
  markers?: TradeMarker[];
  equityData?: EquityPoint[];
  buyHoldData?: EquityPoint[];
  emaLen?: number;
  theme?: 'light' | 'dark';
}

const toKline = (d: ChartData): KLineData => ({
  timestamp: toTs(d.time ?? d.timestamp) * 1000,
  open: d.open, high: d.high, low: d.low, close: d.close, volume: d.volume ?? 0,
});

const toTs = (raw: any): number => {
  if (raw == null || raw === '') return 0;
  if (typeof raw === 'string') { const ms = new Date(raw).getTime(); return Number.isFinite(ms) ? Math.floor(ms / 1000) : 0; }
  const n = Number(raw);
  return Number.isFinite(n) ? (n > 1e11 ? Math.floor(n / 1000) : Math.floor(n)) : 0;
};

const INDICATORS = [
  { id: 'ema', name: 'EMA', overlay: true, enabled: true },
  { id: 'bb', name: 'BOLL', overlay: true, enabled: false },
  { id: 'vwap', name: 'VWAP', overlay: true, enabled: false },
  { id: 'rsi', name: 'RSI', overlay: false, enabled: false },
  { id: 'macd', name: 'MACD', overlay: false, enabled: false },
  { id: 'vol', name: 'VOL', overlay: false, enabled: true },
];

export const TvBacktestChart: React.FC<TvBacktestChartProps> = ({
  data, markers = [], equityData = [], buyHoldData = [], emaLen = 200,
}) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInst = useRef<Chart | null>(null);
  const [activeIndicators, setActiveIndicators] = useState<Set<string>>(
    () => new Set(INDICATORS.filter(i => i.enabled).map(i => i.id))
  );
  const [isFullscreen, setIsFullscreen] = useState(false);

  const toggleIndicator = useCallback((id: string) => {
    setActiveIndicators(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }, []);

  const toggleFullscreen = useCallback(() => {
    const el = chartRef.current?.parentElement;
    if (!el) return;
    if (!document.fullscreenElement) el.requestFullscreen?.().then(() => setIsFullscreen(true)).catch(() => {});
    else document.exitFullscreen?.().then(() => setIsFullscreen(false)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!chartRef.current || !data || data.length === 0) return;
    if (chartInst.current) { dispose(chartRef.current); chartInst.current = null; }

    const chart = init(chartRef.current, {
      styles: {
        grid: { show: true, horizontal: { color: '#1e222d' }, vertical: { color: '#1e222d' } },
        candle: {
          type: CandleType.CandleSolid,
          bar: { upColor: '#089981', downColor: '#f23645', upBorderColor: '#089981', downBorderColor: '#f23645', upWickColor: '#089981', downWickColor: '#f23645' },
          priceMark: {
            show: true,
            high: { show: true, color: '#787b86', textSize: 10, textOffset: 0, textFamily: 'monospace', textWeight: 'normal' },
            low: { show: true, color: '#787b86', textSize: 10, textOffset: 0, textFamily: 'monospace', textWeight: 'normal' },
            last: {
              show: true, upColor: '#089981', downColor: '#f23645',
              line: { show: true, style: LineType.Dashed, size: 1, dashedValue: [2, 2] },
              text: { show: true, size: 11, color: '#d1d4dc', weight: 'bold', family: 'monospace' },
            },
          },
        },
        indicator: { ohlc: { upColor: 'rgba(8,153,129,0.7)', downColor: 'rgba(242,54,69,0.7)' } },
        xAxis: { show: true, axisLine: { color: '#363c4e' }, tickText: { color: '#787b86', size: 10 }, tickLine: { color: '#363c4e' } },
        yAxis: { show: true, position: YAxisPosition.Right, axisLine: { color: '#363c4e' }, tickText: { color: '#787b86', size: 10 }, tickLine: { color: '#363c4e' }, type: YAxisType.Normal },
        separator: { size: 1, fill: true, activeBackgroundColor: 'rgba(41,98,255,0.16)' },
        crosshair: { show: true, horizontal: { show: true, line: { style: LineType.Dashed, size: 1, color: '#758696', dashedValue: [2, 2] }, text: { show: true, color: '#d1d4dc', size: 10, backgroundColor: '#1e222d' } }, vertical: { show: true, line: { style: LineType.Dashed, size: 1, color: '#758696', dashedValue: [2, 2] }, text: { show: true, color: '#d1d4dc', size: 10, backgroundColor: '#1e222d' } } },
      },
      locale: 'en-US',
    });
    if (!chart) return;
    chartInst.current = chart;

    const sorted = [...data].sort((a, b) => toTs(a.time ?? a.timestamp) - toTs(b.time ?? b.timestamp));
    const klines = sorted.map(toKline).filter(k => k.timestamp > 0);
    chart.applyNewData(klines);

    // ── Overlay indicators (on candle pane) ──
    // isStack=true + no paneOptions = stack on candle pane
    if (activeIndicators.has('ema')) {
      chart.createIndicator({ name: 'EMA', calcParams: [emaLen] }, true, { id: 'candle_pane' });
    }
    if (activeIndicators.has('bb')) {
      chart.createIndicator({ name: 'BOLL', calcParams: [20, 2] }, true, { id: 'candle_pane' });
    }
    if (activeIndicators.has('vwap')) {
      chart.createIndicator({ name: 'VWAP' }, true, { id: 'candle_pane' });
    }

    // ── Sub indicators (own pane) ──
    if (activeIndicators.has('rsi')) {
      chart.createIndicator({ name: 'RSI', calcParams: [14] }, false, { id: 'rsi_pane', height: 80 });
    }
    if (activeIndicators.has('macd')) {
      chart.createIndicator({ name: 'MACD', calcParams: [12, 26, 9] }, false, { id: 'macd_pane', height: 100 });
    }
    if (activeIndicators.has('vol')) {
      chart.createIndicator({ name: 'VOL', calcParams: [20] }, false, { id: 'vol_pane', height: 80 });
    }

    // ── Trade markers ──
    if (markers.length > 0) {
      const withPrice = markers
        .filter(m => toTs(m.time) > 0 && (m as any).price > 0)
        .map(m => ({
          name: 'simpleAnnotation',
          needDefaultPointFigure: true,
          needDefaultXAxisFigure: true,
          styles: { content: m.text || '', color: m.color || '#2962FF', size: 12 },
          point: { timestamp: toTs(m.time) * 1000, value: (m as any).price },
        }));
      if (withPrice.length > 0) chart.createOverlay(withPrice);

      // Markers without price: find candle high/low
      const noPrice = markers.filter(m => toTs(m.time) > 0 && !(m as any).price);
      if (noPrice.length > 0) {
        const fallback = noPrice.map(m => {
          const ts = toTs(m.time) * 1000;
          const k = klines.find(k => k.timestamp === ts);
          const val = m.position === 'belowBar' ? (k?.low ?? 0) : (k?.high ?? 0);
          return {
            name: 'simpleAnnotation',
            needDefaultPointFigure: true,
            needDefaultXAxisFigure: true,
            styles: { content: m.text || '', color: m.color || '#2962FF', size: 12 },
            point: { timestamp: ts, value: val },
          };
        }).filter(d => d.point.value > 0);
        if (fallback.length > 0) chart.createOverlay(fallback);
      }
    }

    return () => { if (chartRef.current) dispose(chartRef.current); chartInst.current = null; };
  }, [data, markers, emaLen, activeIndicators, equityData, buyHoldData]);

  if (data.length === 0) {
    return (
      <div className="flex h-[400px] w-full items-center justify-center bg-surface text-sm text-textSecondary">
        No backtest data
      </div>
    );
  }

  return (
    <div className={`w-full bg-[#131722] select-none ${isFullscreen ? 'fixed inset-0 z-50 p-4 overflow-auto' : ''}`}>
      <div className="flex items-center justify-between px-4 py-1.5 border-b border-[#2a2e39]">
        <div className="flex items-center gap-1.5 text-[10px] font-mono text-[#787b86]">
          <span className="font-semibold uppercase tracking-wider text-[#363c4e]">Chart</span>
        </div>
        <div className="flex items-center gap-1 flex-wrap justify-end">
          {INDICATORS.map(ind => (
            <button key={ind.id} onClick={() => toggleIndicator(ind.id)}
              className={`px-1.5 py-0.5 text-[10px] font-mono rounded-sm border transition-colors ${
                activeIndicators.has(ind.id)
                  ? 'border-[#2962FF]/30 bg-[#2962FF]/10 text-[#2962FF]'
                  : 'border-[#2a2e39] text-[#787b86] hover:text-[#d1d4dc]'
              }`}>
              {ind.name}
            </button>
          ))}
          <button onClick={toggleFullscreen}
            className="px-2 py-0.5 text-[10px] font-mono rounded-sm border border-[#2a2e39] text-[#787b86] hover:text-[#d1d4dc] transition-colors ml-1">
            ⛶
          </button>
        </div>
      </div>
      <div ref={chartRef} className="w-full" style={{ height: isFullscreen ? 'calc(100vh - 40px)' : '500px' }} />
    </div>
  );
};

export default React.memo(TvBacktestChart);
