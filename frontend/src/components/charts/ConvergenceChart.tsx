'use client';

import React, { useEffect, useRef } from 'react';
import { createChart, IChartApi, UTCTimestamp } from 'lightweight-charts';

interface Trial {
  score: number;
}

interface Props {
  trials: Trial[];
}

export const ConvergenceChart: React.FC<Props> = ({ trials }) => {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!ref.current || !trials.length) return;
    const chart = createChart(ref.current, {
      layout: { background: { color: 'transparent' }, textColor: '#8b8b8b' },
      grid: { vertLines: { color: 'rgba(255,255,255,0.04)' }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.08)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.08)' },
      width: ref.current.clientWidth,
      height: 220,
    });
    chartRef.current = chart;
    const series = chart.addLineSeries({ color: '#5b9dff', lineWidth: 2 });
    let best = -Infinity;
    const data = trials.map((t, i) => {
      best = Math.max(best, t.score);
      return { time: (i * 3600) as UTCTimestamp, value: best };
    });
    series.setData(data);
    const onResize = () => { if (ref.current) chart.applyOptions({ width: ref.current.clientWidth }); };
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      chart.remove();
    };
  }, [trials]);

  return <div ref={ref} className="w-full" />;
};
