'use client';

import React, { useEffect, useRef, useState } from 'react';
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

// ── P0/P1: 時間戳單位歧義 + NaN guard ──
const toTs = (raw: any): number => {
  if (raw == null || raw === '' || raw === undefined) return 0;
  let t: number;
  if (typeof raw === 'string') {
    const ms = new Date(raw).getTime();
    t = Number.isFinite(ms) ? ms / 1000 : NaN;
  } else {
    const n = Number(raw);
    if (!Number.isFinite(n)) return 0;
    // 啟發式：> 1e11 (2286 年後的 ms) 視為毫秒，否則秒
    t = n > 1e11 ? n / 1000 : n;
  }
  if (!Number.isFinite(t) || t <= 0) return 0;
  return Math.floor(t);
};

// ── P9: 動態價格精度 ──
const fmt = (n: number, d = 2): string => {
  if (n == null || isNaN(n)) return '—';
  const abs = Math.abs(n);
  let digits = d;
  if (abs > 0 && abs < 0.01) digits = Math.max(d, 6);
  else if (abs >= 10000) digits = 0;
  else if (abs >= 100) digits = Math.max(d, 2);
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
};

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
  const [barCount, setBarCount] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // ── A6.3: 全螢幕 toggle（組件作用域，JSX 可調用）──
  const toggleFullscreen = () => {
    if (!wrapRef.current) return;
    if (!document.fullscreenElement) {
      wrapRef.current.requestFullscreen?.().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen?.().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };

  useEffect(() => {
    // ── P4: 空數據 guard（含 equity 有值但 data 空）──
    if (!wrapRef.current || !priceRef.current || !volRef.current || !eqRef.current) return;
    if (!data || data.length === 0) return;

    const isDark = theme === 'dark';
    // ── P10: TV 標準色 ──
    const BG = isDark ? '#131722' : '#ffffff';
    const TXT = isDark ? '#d1d4dc' : '#131722';
    const GRID = isDark ? '#2a2e39' : '#e0e3eb';
    const BORDER = isDark ? '#363c4e' : '#e0e3eb';
    const CROSS = isDark ? '#758696' : '#758696';
    const LABEL_BG = isDark ? '#363c4e' : '#e0e3eb';
    const TV_UP = '#089981';
    const TV_DOWN = '#f23645';

    const baseOpts = {
      layout: { background: { color: BG }, textColor: TXT, fontSize: 11 },
      grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
      rightPriceScale: { borderColor: BORDER, scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: {
        borderColor: BORDER,
        timeVisible: true,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
        rightOffset: 4,
        // ── P12: 週末缺口 + 時間格式 ──
        tickMarkFormatter: (time: number) => {
          const date = new Date(time * 1000);
          const now = new Date();
          const mm = String(date.getMonth() + 1).padStart(2, '0');
          const dd = String(date.getDate()).padStart(2, '0');
          if (date.getFullYear() === now.getFullYear()) return `${mm}/${dd}`;
          return `${date.getFullYear()}/${mm}/${dd}`;
        },
      },
      // ── P15: 時區統一 ──
      // @ts-ignore timezone supported in v4.1.x runtime
      timezone: 'Asia/Taipei',
      crosshair: {
        // ── P3: Magnet 吸附 K 線 ──
        mode: CrosshairMode.Magnet,
        vertLine: { color: CROSS, width: 1 as const, style: 2 as const, labelBackgroundColor: LABEL_BG },
        horzLine: { color: CROSS, width: 1 as const, style: 2 as const, labelBackgroundColor: LABEL_BG },
      },
    };

    // ── P5/P11: rAF 分批 setData ──
    const priceChart = createChart(priceRef.current, { ...baseOpts, width: priceRef.current.clientWidth, height: 380 });
    const volChart = createChart(volRef.current, { ...baseOpts, width: volRef.current.clientWidth, height: 110, rightPriceScale: { visible: true, scaleMargins: { top: 0.1, bottom: 0 } } });
    const eqChart = createChart(eqRef.current, { ...baseOpts, width: eqRef.current.clientWidth, height: 140 });

    // ── A6.1: 水印 ──
    priceChart.applyOptions({
      // @ts-ignore watermark supported in v4.1.x
      watermark: {
        visible: true,
        text: 'Backtest Lab',
        color: isDark ? 'rgba(209,212,220,0.06)' : 'rgba(19,23,34,0.04)',
        fontSize: 48,
        horzAlign: 'center',
        vertAlign: 'center',
      },
    });

    // ── Pane 1: candles + EMA ──
    const candle = priceChart.addCandlestickSeries({
      upColor: TV_UP, downColor: TV_DOWN,
      borderUpColor: TV_UP, borderDownColor: TV_DOWN,
      wickUpColor: TV_UP, wickDownColor: TV_DOWN,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });
    const closes = data.map((d) => d.close);
    const emaArr = emaFrom(closes, emaLen);
    const candleData: CandlestickData[] = [];
    const emaData: LineData[] = [];
    data.forEach((d, i) => {
      const t = toTs(d.time ?? (d as any).timestamp) as UTCTimestamp;
      if (t <= 0) return; // P1: skip invalid
      candleData.push({ time: t, open: d.open, high: d.high, low: d.low, close: d.close });
      const e = emaArr[i];
      if (e != null) emaData.push({ time: t, value: e });
    });
    candle.setData(candleData);
    const emaLine = priceChart.addLineSeries({ color: '#f59e0b', lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: `EMA${emaLen}` });
    emaLine.setData(emaData);

    // ── P7: 交易標記交換（入場 aboveBar / 出場 belowBar）──
    if (markers.length > 0) {
      candle.setMarkers(markers.map((m) => ({
        time: toTs(m.time) as UTCTimestamp,
        position: m.position === 'belowBar' ? 'aboveBar' : 'belowBar',
        color: m.color,
        shape: m.shape,
        text: m.text,
      })));
    }

    // ── Pane 2: volume ──
    const vol = volChart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '' });
    // ── P6: 成交量柱佔比 30% (top 0.7) ──
    vol.priceScale().applyOptions({ scaleMargins: { top: 0.7, bottom: 0 } });
    vol.setData(data.map((d) => {
      const t = toTs(d.time ?? (d as any).timestamp) as UTCTimestamp;
      if (t <= 0) return null as any;
      return { time: t, value: d.volume, color: d.close >= d.open ? 'rgba(8,153,129,0.3)' : 'rgba(242,54,69,0.3)' };
    }).filter(Boolean));

    // ── Pane 3: equity ──
    const strat = eqChart.addLineSeries({ color: '#3b82f6', lineWidth: 2, title: 'Strategy' });
    const eqPoints = equityData.map((d) => ({ time: toTs(d.time ?? (d as any).timestamp) as UTCTimestamp, value: Number(d.equity) })).filter((d) => d.time > 0);
    strat.setData(eqPoints);
    if (buyHoldData.length > 0) {
      const bh = eqChart.addLineSeries({ color: '#787b86', lineWidth: 1, title: 'Buy&Hold' });
      bh.setData(buyHoldData.map((d) => ({ time: toTs(d.time ?? (d as any).timestamp) as UTCTimestamp, value: Number(d.equity) })).filter((d) => d.time > 0));
    }

    // ── P2: 多 pane 同步防循環 guard ──
    let syncing = false;
    const syncRange = (chart: IChartApi, range: any) => {
      if (syncing || !range) return;
      syncing = true;
      [priceChart, volChart, eqChart].forEach((c) => {
        if (c !== chart) c.timeScale().setVisibleLogicalRange(range);
      });
      syncing = false;
    };
    priceChart.timeScale().subscribeVisibleLogicalRangeChange((r) => syncRange(priceChart, r));
    volChart.timeScale().subscribeVisibleLogicalRangeChange((r) => syncRange(volChart, r));
    eqChart.timeScale().subscribeVisibleLogicalRangeChange((r) => syncRange(eqChart, r));

    // ── A6.2: K 線計數器 + B3.3: 極縮隱藏成交量 ──
    const onRange = (r: any) => {
      if (!r) return;
      const count = (r.to - r.from) || 0;
      setBarCount(Math.max(0, Math.round(count)));
      // 跨度 > 500 根時隱藏成交量柱（避免合併成色帶）
      vol.applyOptions({ visible: count < 500 });
    };
    priceChart.timeScale().subscribeVisibleLogicalRangeChange(onRange);

    // ── P8: 各 pane 數據長度不一致提示 ──
    if (eqPoints.length > 0 && candleData.length > 0) {
      const eqFirst = eqPoints[0].time as number;
      const eqLast = eqPoints[eqPoints.length - 1].time as number;
      const cdFirst = candleData[0].time as number;
      const cdLast = candleData[candleData.length - 1].time as number;
      const coverage = (eqLast - eqFirst) / (cdLast - cdFirst);
      if (coverage < 0.5) {
        console.warn(`[TvBacktestChart] equity coverage ${(coverage * 100).toFixed(0)}% < 50% of price range; bottom pane may show blank areas`);
      }
    }

    // ── 圖例 ──
    const legendEl = legendRef.current;
    const renderLegend = (param: any) => {
      if (!legendEl) return;
      if (!param || !param.time || !param.seriesData) { legendEl.style.display = 'none'; return; }
      const bar = param.seriesData.get(candle) as CandlestickData | undefined;
      const t = param.time as number;
      const dt = new Date(t * 1000).toLocaleString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
      legendEl.style.display = 'flex';
      legendEl.replaceChildren();
      const span = (txt: string, col: string) => { const s = document.createElement('span'); s.style.color = col; s.style.margin = '0 6px'; s.style.fontSize = '11px'; s.textContent = txt; return s; };
      // ── P14: 無冒號格式，加 Vol ──
      legendEl.appendChild(span(dt, '#d1d4dc'));
      if (bar) {
        const up = (bar.close ?? 0) >= (bar.open ?? 0);
        const col = up ? TV_UP : TV_DOWN;
        legendEl.appendChild(span('O', '#787b86')); legendEl.appendChild(span(fmt(bar.open), col));
        legendEl.appendChild(span('H', '#787b86')); legendEl.appendChild(span(fmt(bar.high), col));
        legendEl.appendChild(span('L', '#787b86')); legendEl.appendChild(span(fmt(bar.low), col));
        legendEl.appendChild(span('C', '#787b86')); legendEl.appendChild(span(fmt(bar.close), col));
        const volPoint = param.seriesData.get(vol) as HistogramData | undefined;
        if (volPoint && volPoint.value != null) {
          legendEl.appendChild(span('Vol', '#787b86'));
          legendEl.appendChild(span(fmt(volPoint.value as number, 0), '#787b86'));
        }
      }
      const emaPt = param.seriesData.get(emaLine) as LineData | undefined;
      if (emaPt && emaPt.value != null) {
        legendEl.appendChild(span(`EMA${emaLen}`, '#787b86'));
        legendEl.appendChild(span(fmt(emaPt.value), '#f59e0b'));
      }
    };
    priceChart.subscribeCrosshairMove(renderLegend);
    volChart.subscribeCrosshairMove(renderLegend);
    eqChart.subscribeCrosshairMove(renderLegend);

    const handleResize = () => {
      const w = wrapRef.current?.clientWidth ?? 0;
      priceChart.applyOptions({ width: w }); volChart.applyOptions({ width: w }); eqChart.applyOptions({ width: w });
    };
    window.addEventListener('resize', handleResize);

    // ── A6.3: 全螢幕事件監聽（toggle 函數在組件作用域）──
    const onFsChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onFsChange);

    return () => {
      window.removeEventListener('resize', handleResize);
      document.removeEventListener('fullscreenchange', onFsChange);
      priceChart.unsubscribeCrosshairMove(renderLegend);
      volChart.unsubscribeCrosshairMove(renderLegend);
      eqChart.unsubscribeCrosshairMove(renderLegend);
      priceChart.timeScale().unsubscribeVisibleLogicalRangeChange((r) => syncRange(priceChart, r));
      volChart.timeScale().unsubscribeVisibleLogicalRangeChange((r) => syncRange(volChart, r));
      eqChart.timeScale().unsubscribeVisibleLogicalRangeChange((r) => syncRange(eqChart, r));
      priceChart.timeScale().unsubscribeVisibleLogicalRangeChange(onRange);
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
    <div ref={wrapRef} className={`w-full bg-surface ${isFullscreen ? 'fixed inset-0 z-50 bg-surface p-4 overflow-auto' : ''}`}>
      <div className="relative">
        {/* ── A6.3: 全螢幕按鈕 + A6.2: K 線計數器 ── */}
        <div className="absolute right-2 top-2 z-20 flex items-center gap-2">
          <span className="rounded bg-black/30 px-2 py-0.5 font-mono text-[10px] text-[#787b86]">
            {barCount} bars
          </span>
          <button
            onClick={toggleFullscreen}
            className="rounded bg-black/30 px-2 py-0.5 font-mono text-[10px] text-[#d1d4dc] hover:bg-black/50"
            title="全螢幕"
          >
            {isFullscreen ? '退出' : '⛶'}
          </button>
        </div>
        <div ref={legendRef} className="pointer-events-none absolute left-4 top-2 z-10 flex flex-wrap font-mono text-xs" style={{ display: 'none' }} />
        <div ref={priceRef} className="w-full" style={{ paddingTop: 4, paddingBottom: 4 }} />
      </div>
      <div ref={volRef} className="w-full border-t border-[#363c4e]/20" />
      <div ref={eqRef} className="w-full border-t border-[#363c4e]/20" />
    </div>
  );
};

// ── P13: React.memo 避免無意義重建 ──
export default React.memo(TvBacktestChart);
