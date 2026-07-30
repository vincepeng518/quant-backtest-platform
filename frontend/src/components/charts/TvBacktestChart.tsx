'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
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

const TV_BG = '#131722';
const TV_SURFACE = '#1e222d';
const TV_GRID = '#2a2e39';
const TV_BORDER = '#363c4e';
const TV_TEXT = '#d1d4dc';
const TV_SUBTEXT = '#787b86';
const TV_UP = '#089981';
const TV_DOWN = '#f23645';
const TV_EMA = '#f0b90b';
const TV_STRATEGY = '#2962FF';
const TV_LIGHT_BG = '#ffffff';
const TV_LIGHT_GRID = '#e0e3eb';
const TV_LIGHT_BORDER = '#e0e3eb';
const TV_LIGHT_TEXT = '#131722';

const toTs = (raw: any): number => {
  if (raw == null || raw === '') return 0;
  if (typeof raw === 'string') {
    const ms = new Date(raw).getTime();
    return Number.isFinite(ms) ? Math.floor(ms / 1000) : 0;
  }
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0;
  return n > 1e11 ? Math.floor(n / 1000) : Math.floor(n);
};

const sortDedupe = <T extends Record<string, any>>(arr: T[]): T[] => {
  const seen = new Set<number>();
  return [...(arr || [])]
    .sort((a, b) => toTs(a.time ?? a.timestamp) - toTs(b.time ?? b.timestamp))
    .filter((d) => {
      const t = toTs(d.time ?? d.timestamp);
      if (t <= 0 || seen.has(t)) return false;
      seen.add(t);
      return true;
    });
};

const fmt = (n: number, d = 2): string => {
  if (n == null || isNaN(n)) return '—';
  const abs = Math.abs(n);
  let digits = d;
  if (abs > 0 && abs < 0.01) digits = 6;
  else if (abs >= 10000) digits = 0;
  else if (abs >= 100) digits = Math.max(d, 2);
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
};

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
  const containerRef = useRef<HTMLDivElement>(null);
  const priceRef = useRef<HTMLDivElement>(null);
  const volRef = useRef<HTMLDivElement>(null);
  const eqRef = useRef<HTMLDivElement>(null);
  const legendRef = useRef<HTMLDivElement>(null);
  const [barCount, setBarCount] = useState(0);
  const [showEma, setShowEma] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const toggleFullscreen = useCallback(() => {
    const el = containerRef.current?.parentElement;
    if (!el) return;
    if (!document.fullscreenElement) {
      el.requestFullscreen?.().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen?.().then(() => setIsFullscreen(false)).catch(() => {});
    }
  }, []);

  useEffect(() => {
    if (!priceRef.current || !volRef.current || !eqRef.current) return;
    if (!data || data.length === 0) return;

    const isDark = theme === 'dark';
    const BG = isDark ? TV_BG : TV_LIGHT_BG;
    const TXT = isDark ? TV_TEXT : TV_LIGHT_TEXT;
    const GR = isDark ? TV_GRID : TV_LIGHT_GRID;
    const BD = isDark ? TV_BORDER : TV_LIGHT_BORDER;
    const CX = isDark ? '#758696' : '#9b9fa8';
    const LB = isDark ? '#363c4e' : '#d1d4dc';

    // Pane labels — TV style
    const paneLabels = [
      { ref: priceRef, label: '💰 Price · Backtest', height: 360 },
      { ref: volRef, label: '📊 Volume', height: 90 },
      { ref: eqRef, label: '📈 Equity', height: 120 },
    ];

    const baseOpts: any = {
      layout: { background: { type: 'solid', color: BG }, textColor: TXT, fontSize: 11 },
      grid: { vertLines: { color: GR }, horzLines: { color: GR } },
      rightPriceScale: { borderColor: BD, scaleMargins: { top: 0.05, bottom: 0.05 } },
      timeScale: {
        borderColor: BD,
        timeVisible: true,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
        rightOffset: 3,
        tickMarkFormatter: (time: number) => {
          const d = new Date(time * 1000);
          const now = new Date();
          const mm = String(d.getMonth() + 1).padStart(2, '0');
          const dd = String(d.getDate()).padStart(2, '0');
          if (d.getFullYear() === now.getFullYear()) return `${mm}/${dd}`;
          return `${d.getFullYear()}/${mm}/${dd}`;
        },
      },
      timezone: 'Asia/Taipei',
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: CX, width: 1, style: 2, labelBackgroundColor: LB },
        horzLine: { color: CX, width: 1, style: 2, labelBackgroundColor: LB },
      },
      handleScroll: false,
      handleScale: false,
    };

    const priceChart = createChart(priceRef.current, {
      ...baseOpts, width: priceRef.current.clientWidth, height: paneLabels[0].height,
    });

    const volChart = createChart(volRef.current, {
      ...baseOpts, width: volRef.current.clientWidth, height: paneLabels[1].height,
      rightPriceScale: { visible: true, scaleMargins: { top: 0.2, bottom: 0 } },
    });

    const eqChart = createChart(eqRef.current, {
      ...baseOpts, width: eqRef.current.clientWidth, height: paneLabels[2].height,
    });

    // ── Remove LWC attribution ──
    priceChart.applyOptions({ watermark: { visible: false } } as any);
    volChart.applyOptions({ watermark: { visible: false } } as any);
    eqChart.applyOptions({ watermark: { visible: false } } as any);

    // ── Pane 1: Candles ──
    const candle = priceChart.addCandlestickSeries({
      upColor: TV_UP, downColor: TV_DOWN,
      borderUpColor: TV_UP, borderDownColor: TV_DOWN,
      wickUpColor: TV_UP, wickDownColor: TV_DOWN,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });
    const closes = data.map((d) => d.close);
    const emaArr = emaFrom(closes, emaLen);
    const sortedData = sortDedupe(data);
    const candleData: CandlestickData[] = [];
    const emaData: LineData[] = [];
    sortedData.forEach((d, i) => {
      const t = toTs(d.time ?? d.timestamp) as UTCTimestamp;
      if (t <= 0) return;
      candleData.push({ time: t, open: d.open, high: d.high, low: d.low, close: d.close });
      const e = emaArr[i];
      if (e != null) emaData.push({ time: t, value: e });
    });
    candle.setData(candleData);

    const emaLine = priceChart.addLineSeries({
      color: TV_EMA, lineWidth: 1, priceLineVisible: false,
      lastValueVisible: true, title: `EMA ${emaLen}`,
    });
    emaLine.setData(emaData);

    // ── Trade markers ──
    if (markers.length > 0) {
      candle.setMarkers(
        sortDedupe(markers)
          .map((m) => ({
            time: toTs(m.time) as UTCTimestamp,
            position: (m.position === 'belowBar' ? 'aboveBar' : 'belowBar') as 'aboveBar' | 'belowBar',
            color: m.color, shape: m.shape, text: m.text,
          }))
          .filter((m) => m.time > 0)
      );
    }

    // ── Pane 2: Volume ──
    const vol = volChart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '' });
    vol.priceScale().applyOptions({ scaleMargins: { top: 0.5, bottom: 0 } });
    vol.setData(
      sortDedupe(data)
        .map((d) => {
          const t = toTs(d.time ?? d.timestamp) as UTCTimestamp;
          if (t <= 0) return null as any;
          return { time: t, value: d.volume, color: d.close >= d.open ? 'rgba(8,153,129,0.4)' : 'rgba(242,54,69,0.4)' };
        })
        .filter(Boolean)
    );

    // ── Pane 3: Equity ──
    const eq = eqChart.addLineSeries({ color: TV_STRATEGY, lineWidth: 2, title: 'Strategy' });
    const eqPoints = sortDedupe(equityData)
      .map((d) => ({ time: toTs(d.time ?? d.timestamp) as UTCTimestamp, value: Number(d.equity) }))
      .filter((d) => d.time > 0);
    eq.setData(eqPoints);

    // Peak/trough markers on equity
    if (eqPoints.length > 2) {
      let peakVal = -Infinity, peakIdx = 0, maxDd = 0, troughIdx = 0;
      for (let i = 0; i < eqPoints.length; i++) {
        if (eqPoints[i].value > peakVal) { peakVal = eqPoints[i].value; peakIdx = i; }
        const dd = (peakVal - eqPoints[i].value) / peakVal;
        if (dd > maxDd) { maxDd = dd; troughIdx = i; }
      }
      const eqMarkers: any[] = [];
      if (eqPoints[peakIdx]) eqMarkers.push({ time: eqPoints[peakIdx].time, position: 'aboveBar', color: TV_UP, shape: 'circle', text: 'Peak' });
      if (eqPoints[troughIdx] && maxDd > 0.01) eqMarkers.push({ time: eqPoints[troughIdx].time, position: 'belowBar', color: TV_DOWN, shape: 'arrowDown', text: `${(maxDd * 100).toFixed(1)}% DD` });
      if (eqMarkers.length > 0) eq.setMarkers(eqMarkers);
    }

    if (buyHoldData.length > 0) {
      eqChart.addLineSeries({ color: TV_SUBTEXT, lineWidth: 1, title: 'Buy&Hold' })
        .setData(sortDedupe(buyHoldData)
          .map((d) => ({ time: toTs(d.time ?? d.timestamp) as UTCTimestamp, value: Number(d.equity) }))
          .filter((d) => d.time > 0));
    }

    // ── Crosshair sync ──
    let syncing = false;
    const syncRange = (src: IChartApi, range: any) => {
      if (syncing || !range) return;
      syncing = true;
      [priceChart, volChart, eqChart].forEach((c) => { if (c !== src) c.timeScale().setVisibleLogicalRange(range); });
      syncing = false;
    };
    [priceChart, volChart, eqChart].forEach((c) =>
      c.timeScale().subscribeVisibleLogicalRangeChange((r) => syncRange(c, r))
    );

    // ── Bar count + vol hiding ──
    priceChart.timeScale().subscribeVisibleLogicalRangeChange((r: any) => {
      if (!r) return;
      const count = Math.max(0, Math.round((r.to - r.from) || 0));
      setBarCount(count);
      vol.applyOptions({ visible: count < 500 });
    });

    // ── Hover legend ──
    const legendEl = legendRef.current;
    const renderLegend = (param: any) => {
      if (!legendEl) return;
      if (!param || !param.time || !param.seriesData) { legendEl.style.display = 'none'; return; }
      const bar = param.seriesData.get(candle) as CandlestickData | undefined;
      const t = param.time as number;
      const dt = new Date(t * 1000).toLocaleString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
      legendEl.style.display = 'flex';
      legendEl.replaceChildren();
      const mk = (txt: string, col: string, px = '0 6px') => {
        const s = document.createElement('span');
        s.style.cssText = `color:${col};margin:${px};font-size:11px;font-family:'JetBrains Mono',monospace`;
        s.textContent = txt; return s;
      };
      legendEl.appendChild(mk(dt, TXT, '0 8px 0 0'));
      if (bar) {
        const col = (bar.close ?? 0) >= (bar.open ?? 0) ? TV_UP : TV_DOWN;
        legendEl.appendChild(mk('O', TV_SUBTEXT)); legendEl.appendChild(mk(fmt(bar.open), col));
        legendEl.appendChild(mk('H', TV_SUBTEXT)); legendEl.appendChild(mk(fmt(bar.high), col));
        legendEl.appendChild(mk('L', TV_SUBTEXT)); legendEl.appendChild(mk(fmt(bar.low), col));
        legendEl.appendChild(mk('C', TV_SUBTEXT)); legendEl.appendChild(mk(fmt(bar.close), col));
        const vp = param.seriesData.get(vol) as HistogramData | undefined;
        if (vp && vp.value != null) {
          legendEl.appendChild(mk('Vol', TV_SUBTEXT));
          legendEl.appendChild(mk(fmt(vp.value as number, 0), TV_SUBTEXT));
        }
      }
      const ep = param.seriesData.get(emaLine) as LineData | undefined;
      if (ep && ep.value != null && showEma) {
        legendEl.appendChild(mk(`EMA${emaLen}`, TV_SUBTEXT));
        legendEl.appendChild(mk(fmt(ep.value), TV_EMA));
      }
    };
    priceChart.subscribeCrosshairMove(renderLegend);
    volChart.subscribeCrosshairMove(renderLegend);
    eqChart.subscribeCrosshairMove(renderLegend);

    // ── Resize ──
    const handleResize = () => {
      const w = containerRef.current?.clientWidth ?? 0;
      [priceChart, volChart, eqChart].forEach((c, i) => c.applyOptions({ width: w, height: paneLabels[i].height }));
    };
    window.addEventListener('resize', handleResize);

    const onFsChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onFsChange);

    return () => {
      window.removeEventListener('resize', handleResize);
      document.removeEventListener('fullscreenchange', onFsChange);
      [priceChart, volChart, eqChart].forEach((c) => { c.unsubscribeCrosshairMove(renderLegend); c.remove(); });
    };
  }, [data, markers, equityData, buyHoldData, emaLen, theme, showEma]);

  if (data.length === 0) {
    return (
      <div className="flex h-[400px] w-full items-center justify-center bg-surface text-sm text-textSecondary">
        尚無回測數據
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`w-full bg-surface select-none ${isFullscreen ? 'fixed inset-0 z-50 bg-surface p-4 overflow-auto' : ''}`}
    >
      {/* Floating toolbar */}
      <div className="flex items-center justify-between px-5 py-2 border-b border-border/10 bg-surface/80 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-textSecondary/60">Chart</span>
          <span className="text-[10px] font-mono text-textSecondary/40">{barCount} bars</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowEma((v) => !v)}
            className={`px-2 py-0.5 text-[10px] font-mono rounded-sm border transition-colors ${
              showEma
                ? 'border-accent/30 bg-accent/10 text-accent'
                : 'border-border/20 text-textSecondary/60 hover:text-text'
            }`}
          >
            EMA {emaLen}
          </button>
          <button
            onClick={toggleFullscreen}
            className="px-2 py-0.5 text-[10px] font-mono rounded-sm border border-border/20 text-textSecondary/60 hover:text-text transition-colors"
            title="全螢幕"
          >
            ⛶
          </button>
        </div>
      </div>

      {/* Pane labels + legends */}
      <div className="relative">
        <div
          ref={legendRef}
          className="pointer-events-none absolute left-4 top-2 z-10 flex items-center font-mono text-xs tabular-nums"
          style={{ display: 'none' }}
        />
        <div ref={priceRef} className="w-full" />
      </div>
      <div className="relative">
        <span className="absolute left-3 top-1 z-10 font-mono text-[9px] uppercase tracking-widest text-textSecondary/30 pointer-events-none">
          Volume
        </span>
        <div ref={volRef} className="w-full border-t border-border/10" />
      </div>
      <div className="relative">
        <span className="absolute left-3 top-1 z-10 font-mono text-[9px] uppercase tracking-widest text-textSecondary/30 pointer-events-none">
          Equity
        </span>
        <div ref={eqRef} className="w-full border-t border-border/10" />
      </div>
    </div>
  );
};

export default React.memo(TvBacktestChart);
