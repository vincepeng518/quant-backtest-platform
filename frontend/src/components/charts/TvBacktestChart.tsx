'use client';

import React, { useEffect, useRef } from 'react';
import {
  createChart, IChartApi, ISeriesApi, UTCTimestamp,
  CandlestickData, HistogramData, LineData, CrosshairMode,
} from 'lightweight-charts';
import { ChartData, TradeMarker } from '@/types/chart';
import { EquityPoint } from '@/types/api';

interface TvBacktestChartProps {
  data: ChartData[];
  markers?: TradeMarker[];
  equityData?: EquityPoint[];
  buyHoldData?: EquityPoint[];
  emaLen?: number;
  theme?: 'light' | 'dark';
}

const toTs = (raw: any): number => {
  const t = typeof raw === 'string' ? new Date(raw).getTime() / 1000 : Number(raw) / 1000;
  return Math.floor(t);
};

const fmt = (n: number, d = 2) =>
  n == null || isNaN(n) ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

// EMA 递推（前端计算，复用策略默认 200）
function emaFrom(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = [];
  const alpha = 2 / (period + 1);
  let prev: number | null = null;
  let seed = 0;
  for (let i = 0; i < values.length; i++) {
    if (i < period - 1) { out.push(null); seed += values[i]; continue; }
    if (i === period - 1) { seed += values[i]; prev = seed / period; out.push(prev); continue; }
    prev = alpha * values[i] + (1 - alpha) * prev!;
    out.push(prev);
  }
  return out;
}

export const TvBacktestChart: React.FC<TvBacktestChartProps> = ({
  data, markers = [], equityData = [], buyHoldData = [], emaLen = 200, theme = 'dark',
}) => {
  const wrapRef = useRef<HTMLDivElement>(null);
  const priceRef = useRef<HTMLDivElement>(null);
  const volRef = useRef<HTMLDivElement>(null);
  const eqRef = useRef<HTMLDivElement>(null);
  const legendRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!wrapRef.current || !priceRef.current || !volRef.current || !eqRef.current) return;
    if (data.length === 0) return;

    const isDark = theme === 'dark';
    const BG = isDark ? '#0a0a0a' : '#ffffff';
    const TXT = isDark ? '#a3a3a3' : '#525252';
    const GRID = isDark ? '#171717' : '#f5f5f5';
    const BORDER = isDark ? '#262626' : '#e5e5e5';

    const baseOpts = {
      layout: { background: { color: BG }, textColor: TXT },
      grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
      rightPriceScale: { borderColor: BORDER },
      timeScale: { borderColor: BORDER, timeVisible: true, secondsVisible: false },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: TXT, width: 1 as const, style: 2 as const, labelBackgroundColor: '#262626' },
        horzLine: { color: TXT, width: 1 as const, style: 2 as const, labelBackgroundColor: '#262626' },
      },
    };

    const priceChart = createChart(priceRef.current, { ...baseOpts, width: priceRef.current.clientWidth, height: 380 });
    const volChart = createChart(volRef.current, { ...baseOpts, width: volRef.current.clientWidth, height: 110, rightPriceScale: { visible: false } });
    const eqChart = createChart(eqRef.current, { ...baseOpts, width: eqRef.current.clientWidth, height: 140 });

    // ── Pane 1: candles + EMA ──
    const candle = priceChart.addCandlestickSeries({
      upColor: '#10b981', downColor: '#ef4444',
      borderUpColor: '#10b981', borderDownColor: '#ef4444',
      wickUpColor: '#10b981', wickDownColor: '#ef4444',
    });
    const closes = data.map((d) => d.close);
    const emaArr = emaFrom(closes, emaLen);
    const candleData: CandlestickData[] = [];
    const emaData: LineData[] = [];
    data.forEach((d, i) => {
      const t = toTs(d.time ?? (d as any).timestamp) as UTCTimestamp;
      candleData.push({ time: t, open: d.open, high: d.high, low: d.low, close: d.close });
      const e = emaArr[i];
      if (e != null) emaData.push({ time: t, value: e });
    });
    candle.setData(candleData);
    const emaLine = priceChart.addLineSeries({ color: '#f59e0b', lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: `EMA${emaLen}` });
    emaLine.setData(emaData);
    if (markers.length > 0) {
      candle.setMarkers(markers.map((m) => ({ time: toTs(m.time) as UTCTimestamp, position: m.position, color: m.color, shape: m.shape, text: m.text })));
    }

    // ── Pane 2: volume ──
    const vol = volChart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '' });
    vol.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });
    vol.setData(data.map((d) => {
      const t = toTs(d.time ?? (d as any).timestamp) as UTCTimestamp;
      return { time: t, value: d.volume, color: d.close >= d.open ? 'rgba(16,185,129,0.5)' : 'rgba(239,68,68,0.5)' };
    }));

    // ── Pane 3: equity ──
    const strat = eqChart.addLineSeries({ color: '#3b82f6', lineWidth: 2, title: 'Strategy' });
    strat.setData(equityData.map((d) => ({ time: toTs(d.time ?? (d as any).timestamp) as UTCTimestamp, value: Number(d.equity) })).filter((d) => d.time > 0));
    if (buyHoldData.length > 0) {
      const bh = eqChart.addLineSeries({ color: '#a3a3a3', lineWidth: 1, title: 'Buy&Hold' });
      bh.setData(buyHoldData.map((d) => ({ time: toTs(d.time ?? (d as any).timestamp) as UTCTimestamp, value: Number(d.equity) })).filter((d) => d.time > 0));
    }

    // ── 时间轴同步（TV 多 pane）──
    const syncRange = (chart: IChartApi, range: any) => {
      [priceChart, volChart, eqChart].forEach((c) => { if (c !== chart) c.timeScale().setVisibleLogicalRange(range); });
    };
    priceChart.timeScale().subscribeVisibleLogicalRangeChange((r) => r && syncRange(priceChart, r));
    volChart.timeScale().subscribeVisibleLogicalRangeChange((r) => r && syncRange(volChart, r));
    eqChart.timeScale().subscribeVisibleLogicalRangeChange((r) => r && syncRange(eqChart, r));

    // ── 三 pane 时间轴已同步，crosshair 横线各自 pane 显示（TV 标准行为）──

    // ── 图例 ──
    const legendEl = legendRef.current;
    const renderLegend = (param: any) => {
      if (!legendEl) return;
      if (!param || !param.time || !param.seriesData) { legendEl.style.display = 'none'; return; }
      const bar = param.seriesData.get(candle) as CandlestickData | undefined;
      const t = param.time as number;
      const dt = new Date(t * 1000).toLocaleString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
      legendEl.style.display = 'flex';
      legendEl.replaceChildren();
      const span = (txt: string, col: string) => { const s = document.createElement('span'); s.style.color = col; s.style.margin = '0 6px'; s.textContent = txt; return s; };
      legendEl.appendChild(span(dt, '#a3a3a3'));
      if (bar) {
        const up = (bar.close ?? 0) >= (bar.open ?? 0);
        const col = up ? '#10b981' : '#ef4444';
        legendEl.appendChild(span('O', '#a3a3a3')); legendEl.appendChild(span(fmt(bar.open), col));
        legendEl.appendChild(span('H', '#a3a3a3')); legendEl.appendChild(span(fmt(bar.high), col));
        legendEl.appendChild(span('L', '#a3a3a3')); legendEl.appendChild(span(fmt(bar.low), col));
        legendEl.appendChild(span('C', '#a3a3a3')); legendEl.appendChild(span(fmt(bar.close), col));
      }
      const emaPt = param.seriesData.get(emaLine) as LineData | undefined;
      if (emaPt) legendEl.appendChild(span(`EMA${emaLen}`, '#a3a3a3')), legendEl.appendChild(span(fmt(emaPt.value), '#f59e0b'));
    };
    priceChart.subscribeCrosshairMove(renderLegend);
    volChart.subscribeCrosshairMove(() => {});
    eqChart.subscribeCrosshairMove(() => {});

    const handleResize = () => {
      const w = wrapRef.current?.clientWidth ?? 0;
      priceChart.applyOptions({ width: w }); volChart.applyOptions({ width: w }); eqChart.applyOptions({ width: w });
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      priceChart.remove(); volChart.remove(); eqChart.remove();
    };
  }, [data, markers, equityData, buyHoldData, emaLen, theme]);

  if (data.length === 0) {
    return (
      <div className="flex h-[400px] w-full items-center justify-center bg-surface text-sm text-textSecondary">
        尚無回測數據 · 執行回測後顯示 TV 級圖表
      </div>
    );
  }

  return (
    <div ref={wrapRef} className="w-full bg-surface">
      <div className="relative">
        <div ref={legendRef} className="pointer-events-none absolute left-4 top-2 z-10 flex font-mono text-xs" style={{ display: 'none' }} />
        <div ref={priceRef} className="w-full" />
      </div>
      <div ref={volRef} className="w-full border-t border-border/10" />
      <div ref={eqRef} className="w-full border-t border-border/10" />
    </div>
  );
};
