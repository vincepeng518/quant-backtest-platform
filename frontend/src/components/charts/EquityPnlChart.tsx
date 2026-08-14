'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart, UTCTimestamp, IChartApi,
  LineData, HistogramData, CrosshairMode,
} from 'lightweight-charts';
import { EquityPoint, TradeRecord } from '@/types/api';
import { TV_UP, TV_DOWN, TV_STRATEGY, TV_BH } from '@/lib/format';

const BH_GRAY = TV_BH;

const UP_RGB = '8,153,129';
const DOWN_RGB = '242,54,69';

interface Props {
  equity: EquityPoint[];
  buyHold?: EquityPoint[];
  trades?: TradeRecord[];
  initialCapital: number;
  showBuyHold: boolean;
  showSpread?: boolean;
  currency?: string; // 幣種標示(USDT/USD),圖表 Initial 標籤連動
  theme?: 'light' | 'dark';
}

const toU = (v: any): number => {
  if (v == null || v === '') return 0;
  if (typeof v === 'number') return v > 1e11 ? Math.floor(v / 1000) : Math.floor(v);
  const ms = Date.parse(v);
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : 0;
};

export const EquityPnlChart: React.FC<Props> = ({
  equity, buyHold = [], trades = [], initialCapital,
  showBuyHold, currency = 'USDT', theme = 'dark',
}) => {
  const [isFS, setFS] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // TV-style layer visibility
  const [showEq, setShowEq] = useState(true);
  const [showBh, setShowBh] = useState(true);
  const [showPnl, setShowPnl] = useState(true);
  const [showPct, setShowPct] = useState(false);

  const CHART_H = 380;

  useEffect(() => {
    if (!containerRef.current) return;
    if (!equity || equity.length < 2) return;

    const isDark = theme === 'dark';
    const BG = isDark ? '#131722' : '#fff';
    const TXT = isDark ? '#d1d4dc' : '#131722';
    const GR = isDark ? 'rgba(42,46,57,0.4)' : 'rgba(224,227,235,0.6)';
    const BD = isDark ? '#363c4e' : '#d1d4dc';
    const CX = isDark ? '#758696' : '#9b9fa8';

    // ── Build equity data ──
    const eqRaw: { t: number; v: number }[] = equity
      .map((d) => {
        const t = toU(d.time ?? d.timestamp);
        const v = Number(d.equity);
        return t > 0 && Number.isFinite(v) ? { t, v } : null;
      })
      .filter(Boolean) as any;

    if (eqRaw.length < 2) return;

    // ── Detect trade range and clip ──
    let tMin = Infinity, tMax = 0;
    for (const t of trades || []) {
      const u = toU(t.exit_time);
      if (u) { tMin = Math.min(tMin, u); tMax = Math.max(tMax, u); }
    }
    if (tMin === Infinity && buyHold.length > 0) {
      for (const d of buyHold) {
        const u = toU(d.time ?? d.timestamp);
        if (u) { tMin = Math.min(tMin, u); tMax = Math.max(tMax, u); }
      }
    }
    if (tMin === Infinity) {
      for (const d of eqRaw) {
        if (Math.abs(d.v - initialCapital) > initialCapital * 0.001) {
          tMin = Math.min(tMin, d.t); tMax = Math.max(tMax, d.t);
        }
      }
    }

    let eqClipped = eqRaw;
    if (tMin < Infinity && tMax > tMin) {
      const pad = (tMax - tMin) * 0.03;
      const f = eqRaw.filter((d: any) => d.t >= tMin - pad && d.t <= tMax + pad);
      if (f.length > 5) eqClipped = f;
    }
    if (eqClipped.length > 3000) eqClipped = eqClipped.slice(-3000);

    const eqData: LineData[] = eqClipped.map((d: any) => ({
      time: d.t as UTCTimestamp,
      value: showPct ? ((d.v - initialCapital) / initialCapital) * 100 : d.v,
    }));

    // ── Single chart (TV style) ──
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth, height: CHART_H,
      layout: {
        background: { type: 'solid', color: BG } as any,
        textColor: TXT, fontSize: 11,
      },
      grid: { vertLines: { color: GR }, horzLines: { color: GR } },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: CX, width: 1 as const, style: 2 as const, labelBackgroundColor: BD },
        horzLine: { color: CX, width: 1 as const, style: 2 as const, labelBackgroundColor: BD },
      },
      timeScale: {
        borderColor: BD, timeVisible: true, secondsVisible: false,
        fixLeftEdge: true, fixRightEdge: true,
        timezone: 'Asia/Taipei',
      } as any,
      rightPriceScale: {
        borderColor: BD, scaleMargins: { top: 0.05, bottom: 0.25 },
      },
    });

    chart.applyOptions({ watermark: { visible: false } as any });

    // ── Equity line (main) ──
    const eqLine = chart.addLineSeries({
      color: TV_STRATEGY, lineWidth: 2, title: 'Equity',
      priceLineVisible: false, lastValueVisible: true,
    });
    eqLine.setData(eqData);

    // Initial capital line
    const initVal = showPct ? 0 : initialCapital;
    eqLine.createPriceLine({
      price: initVal, color: BH_GRAY, lineWidth: 1, lineStyle: 2,
      axisLabelVisible: true, title: showPct ? '0%' : `Initial (${currency})`,
    });

    // Peak/trough markers
    let pv = -Infinity, pi = -1, md = 0, ti = -1;
    for (let i = 0; i < eqData.length; i++) {
      if (eqData[i].value > pv) { pv = eqData[i].value; pi = i; }
      const dd = (pv - eqData[i].value) / (pv || 1);
      if (dd > md) { md = dd; ti = i; }
    }
    const mks: any[] = [];
    if (pi >= 0) mks.push({
      time: eqData[pi].time, position: 'belowBar', color: TV_UP,
      shape: 'arrowUp', text: `${showPct ? '+' : ''}${pv.toFixed(showPct ? 2 : 0)}`,
    });
    if (ti >= 0 && md > 0.005) mks.push({
      time: eqData[ti].time, position: 'aboveBar', color: TV_DOWN,
      shape: 'arrowDown', text: `${(-md * 100).toFixed(1)}%`,
    });
    if (mks.length) eqLine.setMarkers(mks);

    // ── Buy & Hold ──
    if (showBuyHold && buyHold.length > 0) {
      const bhSeries = chart.addLineSeries({
        color: BH_GRAY, lineWidth: 1, title: 'B&H',
        priceLineVisible: false, lastValueVisible: false,
      });
      bhSeries.setData(
        buyHold
          .map((d) => {
            const t = toU(d.time ?? d.timestamp);
            const v = Number(d.equity);
            return t > 0 && Number.isFinite(v)
              ? { time: t as UTCTimestamp, value: showPct ? ((v - initialCapital) / initialCapital) * 100 : v }
              : null;
          })
          .filter(Boolean) as LineData[]
      );
    }

    // ── Trade PnL bars (bottom 20% of chart, TV style) ──
    const pnlSeries = chart.addHistogramSeries({
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
      priceScaleId: 'pnl',
      title: 'PnL',
    });
    pnlSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    const bars = [...(trades || [])]
      .sort((a, b) => toU(a.exit_time) - toU(b.exit_time))
      .map((t) => {
        const p = Number(t.pnl) || 0;
        const tt = toU(t.exit_time);
        if (!tt) return null;
        const val = showPct ? (p / initialCapital) * 100 : p;
        return { time: tt as UTCTimestamp, value: val, color: val >= 0 ? `rgba(${UP_RGB},0.55)` : `rgba(${DOWN_RGB},0.55)` };
      })
      .filter(Boolean) as HistogramData[];

    if (bars.length > 0) {
      const r0 = eqData[0].time as number;
      const r1 = eqData[eqData.length - 1].time as number;
      pnlSeries.setData(bars.filter((d) => (d.time as number) >= r0 && (d.time as number) <= r1));
    }

    // ── Fit content ──
    setTimeout(() => chart.timeScale().fitContent(), 30);

    // ── Resize ──
    const hr = () => chart.applyOptions({ width: containerRef.current?.clientWidth ?? 0 });
    window.addEventListener('resize', hr);
    const fs = () => setFS(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', fs);

    return () => {
      window.removeEventListener('resize', hr);
      document.removeEventListener('fullscreenchange', fs);
      chart.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [equity, buyHold, trades, initialCapital, showBuyHold, showPct, theme]);

  return (
    <div className={`w-full bg-[#131722] select-none ${isFS ? 'fixed inset-0 z-50 p-4 overflow-auto' : ''}`}>
      {/* TV-style top bar */}
      <div className="flex items-center justify-between px-4 py-1.5 border-b border-[#363c4e]/40 bg-[#131722]">
        {/* Left: layer toggles — TV style pill buttons */}
        <div className="flex items-center gap-0.5">
          <button
            onClick={() => setShowEq((v) => !v)}
            className={`px-2.5 py-0.5 text-[10px] font-mono rounded-sm border transition-all duration-100 ${
              showEq
                ? 'border-[#c9a962]/50 bg-[#c9a962]/10 text-[#c9a962]'
                : 'border-transparent text-[#787b86] hover:text-[#d1d4dc]'
            }`}
          >
            ● Equity
          </button>
          <button
            onClick={() => setShowBh((v) => !v)}
            className={`px-2.5 py-0.5 text-[10px] font-mono rounded-sm border transition-all duration-100 ${
              showBh
                ? 'border-[#787b86]/50 bg-[#787b86]/10 text-[#d1d4dc]'
                : 'border-transparent text-[#787b86] hover:text-[#d1d4dc]'
            }`}
          >
            ○ B&H
          </button>
          <button
            onClick={() => setShowPnl((v) => !v)}
            className={`px-2.5 py-0.5 text-[10px] font-mono rounded-sm border transition-all duration-100 ${
              showPnl
                ? 'border-[#089981]/50 bg-[#089981]/10 text-[#089981]'
                : 'border-transparent text-[#787b86] hover:text-[#d1d4dc]'
            }`}
          >
            ▬ PnL
          </button>
        </div>
        {/* Right: absolute/percentage toggle — exact TV style */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowPct(false)}
            className={`px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider transition-colors ${
              !showPct ? 'text-[#d1d4dc] bg-[#363c4e]/40 rounded-sm' : 'text-[#787b86] hover:text-[#d1d4dc]'
            }`}
          >
            Abs
          </button>
          <button
            onClick={() => setShowPct(true)}
            className={`px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider transition-colors ${
              showPct ? 'text-[#d1d4dc] bg-[#363c4e]/40 rounded-sm' : 'text-[#787b86] hover:text-[#d1d4dc]'
            }`}
          >
            %
          </button>
        </div>
      </div>
      <div ref={containerRef} className="w-full" style={{ height: CHART_H }} />
    </div>
  );
};

export default React.memo(EquityPnlChart);
