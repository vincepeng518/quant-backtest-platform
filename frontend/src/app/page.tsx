'use client';

import React from 'react';
import Link from 'next/link';
import { Activity, Sliders, TrendingUp, ArrowRight, Database, Cpu, Gauge, GitCompareArrows } from 'lucide-react';
import { MetricsCard } from '@/components/ui/MetricsCard';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { useDashboard } from '@/lib/dashboard';
import { useMonitor } from '@/lib/monitor';

const modules = [
  {
    name: 'Backtest',
    path: '/backtest',
    icon: Activity,
    tag: '回測引擎',
    desc: '載入市場數據，套用均線交叉、突破、配對交易等策略，秒級生成績效報告與權益曲線。',
    metric: 'P&L',
  },
  {
    name: 'Optimize',
    path: '/optimize',
    icon: Sliders,
    tag: '參數優化',
    desc: '網格搜索、遺傳演算法、貝葉斯優化並行掃參，自動收斂到最佳風險調整後參數組合。',
    metric: 'SHARPE',
  },
  {
    name: 'Arbitrage',
    path: '/arbitrage',
    icon: GitCompareArrows,
    tag: '跨所套利',
    desc: '雙邊持倉捕捉同一資產在不同交易所的價差與資金費率差，合約級手續費與 funding 實景建模。',
    metric: 'BASIS',
  },
  {
    name: 'Monitoring',
    path: '/monitoring',
    icon: GitCompareArrows,
    tag: 'predict.fun 監控',
    desc: '影子交易實時戰績、輪次明細與異常報警。本機守護進程自動重連，數據不假死。',
    metric: 'SHADOW',
  },
];

const capabilities = [
  { icon: Database, label: '多市場數據', detail: 'Crypto · Equity · Futures · FX' },
  { icon: Cpu, label: '向量化引擎', detail: 'pandas / numpy 高速計算' },
  { icon: Gauge, label: 'ML 接口預留', detail: 'StrategyBase 抽象層可擴充' },
];

function StatsStrip() {
  const { loading, error, stats } = useDashboard();
  if (loading) return <Spinner />;
  if (error) return <EmptyState title="無法載入統計" description={error} />;
  const items: { label: string; value: string | number; accent?: 'success' | 'danger' | 'neutral' | 'accent' }[] = [
    { label: '總回測數', value: stats.total },
    { label: '平均 Sharpe', value: stats.avgSharpe ?? '—', accent: (stats.avgSharpe ?? 0) >= 0 ? 'success' : 'danger' },
    { label: '最佳 Sharpe', value: stats.bestRun ? Number(stats.bestRun.sharpe).toFixed(2) : '—', accent: 'success' },
    { label: '最差 Sharpe', value: stats.worstRun ? Number(stats.worstRun.sharpe).toFixed(2) : '—', accent: 'danger' },
  ];
  return <MetricsCard items={items} />;
}

function MonitorStrip() {
  const { stats, loading, error } = useMonitor();
  if (loading) return <Spinner />;
  if (error || !stats?.available || !stats.data) {
    return (
      <div className="rounded-xl border border-border/10 bg-surface/50 p-5">
        <div className="flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-textSecondary">
          <span className="h-1.5 w-1.5 rounded-full bg-accent/60" />
          <span>predict.fun 實時監控</span>
        </div>
        <p className="mt-3 text-sm text-textSecondary">
          {error ? '監控端未連線' : '監控守護進程未啟動 — 本地 daemon 上線後此處顯示真實戰績'}
        </p>
      </div>
    );
  }
  const d = stats.data;
  const items: { label: string; value: string | number; accent?: 'success' | 'danger' | 'neutral' | 'accent' }[] = [
    { label: '影子交易', value: d?.shadow?.resolved ?? 0, accent: 'accent' },
    { label: '勝率', value: `${d?.shadow?.win_rate ?? 0}%`, accent: (d?.shadow?.win_rate ?? 0) >= 50 ? 'success' : 'danger' },
    { label: '累計 P&L', value: d?.shadow?.total_pnl ?? 0, accent: (d?.shadow?.total_pnl ?? 0) >= 0 ? 'success' : 'danger' },
    { label: '尾盤加速', value: d?.tail?.tail_accel ?? '—', accent: 'neutral' },
  ];
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-textSecondary">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
          <span>predict.fun 實時監控</span>
        </div>
        {stats.updated_at && (
          <span className="font-mono text-[10px] text-textSecondary">
            {new Date(stats.updated_at).toLocaleTimeString()}
          </span>
        )}
      </div>
      <MetricsCard items={items} />
    </div>
  );
}

function RecentRuns() {
  const { rows, loading, error } = useDashboard();
  if (loading) return <Spinner />;
  if (error) return <EmptyState title="無法載入紀錄" description={error} />;
  if (rows.length === 0) {
    return <EmptyState title="尚無回測紀錄" description="前往 Backtest 執行第一筆回測" />;
  }
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-accent">近期回測</h3>
      <div className="divide-y divide-border/10">
        {rows.slice(0, 8).map((r) => (
          <Link
            key={r.task_id}
            href={`/backtest?task=${r.task_id}`}
            className="flex items-center justify-between py-3 group hover:bg-surface/50 transition-colors rounded px-2 -mx-2"
          >
            <div className="flex flex-col">
              <span className="font-medium text-text group-hover:text-accent transition-colors">
                {r.symbol ?? '—'} · {r.timeframe ?? ''}
              </span>
              <span className="text-xs text-textSecondary">
                {r.strategy ?? 'strategy'} · {r.created_at?.slice(0, 10)}
              </span>
            </div>
            <div className="flex items-center gap-6 font-mono text-sm">
              <span className="text-textSecondary">{r.total_trades ?? 0} trades</span>
              <span className={(r.sharpe ?? 0) >= 0 ? 'text-success' : 'text-danger'}>
                SR {Number(r.sharpe ?? 0).toFixed(2)}
              </span>
              <ArrowRight className="w-4 h-4 text-textSecondary group-hover:text-accent transition-colors" />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <div className="space-y-24 pb-12">
      {/* ── Hero ── */}
      <section className="relative overflow-hidden min-h-[420px] flex items-center">
        {/* 抽象權益曲線視覺 */}
        <div className="pointer-events-none absolute inset-0 -z-10 opacity-[0.07]">
          <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1200 400" preserveAspectRatio="xMidYMid slice" fill="none">
            <path
              d="M0 320 L120 300 L240 330 L360 250 L480 270 L600 180 L720 210 L840 120 L960 150 L1080 70 L1200 90"
              stroke="var(--accent)"
              strokeWidth="2"
            />
            <path
              d="M0 360 L120 350 L240 365 L360 320 L480 335 L600 280 L720 300 L840 230 L960 250 L1080 190 L1200 200"
              stroke="var(--text)"
              strokeWidth="1"
              opacity="0.5"
            />
          </svg>
        </div>
        <div className="pointer-events-none absolute -top-24 right-0 -z-10 h-96 w-96 rounded-full bg-accent/5 blur-3xl" />

        <div className="w-full max-w-3xl pt-16 md:pt-24">
          <div className="mb-6 flex items-center space-x-2 font-mono text-xs uppercase tracking-[0.2em] text-textSecondary">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            <span>Quantitative Trading Infrastructure</span>
          </div>

          <h1 className="text-4xl font-semibold leading-[1.1] tracking-tight md:text-6xl">
            在市場中
            <br />
            <span className="text-accent">持續賺取 P&L</span>
          </h1>

          <p className="mt-6 max-w-xl text-base leading-relaxed text-textSecondary md:text-lg">
            極簡、高性能的量化回測與優化平台。從策略構想到樣本外驗證，
            一套工具完成全部工作流。數據天賦 × 策略思維 × 高速執行。
          </p>

          <div className="mt-10 flex flex-wrap items-center gap-4">
            <Link
              href="/backtest"
              className="group inline-flex items-center space-x-2 rounded-lg bg-accent px-6 py-3 text-sm font-medium text-white transition-all hover:opacity-90"
            >
              <span>進入平台</span>
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/analysis"
              className="inline-flex items-center space-x-2 rounded-lg bg-surface px-6 py-3 text-sm font-medium text-text transition-colors hover:bg-surface/70"
            >
              <span>穩健性分析</span>
            </Link>
          </div>
        </div>
      </section>

      {/* ── 即時儀表板 ── */}
      <section className="space-y-6">
        <StatsStrip />
        <ErrorBoundary>
          <MonitorStrip />
        </ErrorBoundary>
        <RecentRuns />
      </section>

      {/* ── 三大模塊 ── */}
      <section className="space-y-8">
        <div className="flex items-end justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-textSecondary">
            核心模塊
          </h2>
          <span className="font-mono text-xs text-textSecondary">05 / workflows</span>
        </div>

        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-4">
          {modules.map((m) => {
            const Icon = m.icon;
            return (
              <Link
                key={m.name}
                href={m.path}
                className="group rounded-xl bg-surface p-7 transition-all duration-200 hover:-translate-y-0.5 hover:bg-surface/70"
              >
                <div className="flex items-center justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-background">
                    <Icon className="h-5 w-5 text-accent" />
                  </div>
                  <span className="font-mono text-[10px] uppercase tracking-widest text-textSecondary">
                    {m.metric}
                  </span>
                </div>

                <h3 className="mt-6 text-lg font-semibold tracking-tight">{m.name}</h3>
                <p className="mt-1 font-mono text-xs uppercase tracking-wider text-accent">
                  {m.tag}
                </p>
                <p className="mt-4 text-sm leading-relaxed text-textSecondary">{m.desc}</p>

                <div className="mt-6 flex items-center space-x-1 text-xs font-medium text-textSecondary transition-colors group-hover:text-text">
                  <span>打開</span>
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      {/* ── 能力條 ── */}
      <section className="space-y-8">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-textSecondary">
          平台能力
        </h2>
        <div className="grid grid-cols-1 gap-px md:grid-cols-3">
          {capabilities.map((c) => {
            const Icon = c.icon;
            return (
              <div key={c.label} className="rounded-xl bg-surface p-7">
                <Icon className="h-5 w-5 text-accent" />
                <h3 className="mt-5 text-base font-medium tracking-tight">{c.label}</h3>
                <p className="mt-2 font-mono text-xs text-textSecondary">{c.detail}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── CTA 帶 ── */}
      <section className="relative overflow-hidden rounded-2xl bg-surface px-8 py-14 text-center md:py-20">
        <div className="pointer-events-none absolute -bottom-20 left-1/2 -z-10 h-64 w-64 -translate-x-1/2 rounded-full bg-accent/5 blur-3xl" />
        <h2 className="mx-auto max-w-2xl text-2xl font-semibold leading-tight tracking-tight md:text-3xl">
          紀律就是利潤，情緒就是成本。
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-sm text-textSecondary">
          從第一筆回測開始，建立你的系統化交易優勢。
        </p>
        <Link
          href="/backtest"
          className="group mt-8 inline-flex items-center space-x-2 rounded-lg bg-accent px-6 py-3 text-sm font-medium text-white transition-all hover:opacity-90"
        >
          <span>開始回測</span>
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </section>
    </div>
  );
}