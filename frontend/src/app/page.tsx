'use client';

import React, { useMemo } from 'react';
import Link from 'next/link';
import { ArrowRight, ArrowUpRight } from 'lucide-react';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { APP_VERSION } from '@/lib/version';
import { useDashboard } from '@/lib/dashboard';

/* ── deterministic equity walk seeded by run count — the desk's signature line ── */
function equityPath(seed: number, w = 600, h = 120): { pts: string; len: number } {
  let s = seed * 9301 + 49297;
  const rnd = () => ((s = (s * 233280 + 9301) % 2332800) / 2332800);
  let v = h * 0.72;
  const n = 48;
  const out: string[] = [];
  for (let i = 0; i <= n; i++) {
    const drift = -0.9 - rnd() * 1.6; // upward bias (y is inverted)
    v = Math.max(8, Math.min(h - 8, v + drift + (rnd() - 0.5) * 14));
    out.push(`${((i / n) * w).toFixed(1)},${v.toFixed(1)}`);
  }
  return { pts: out.join(' '), len: w * 2 };
}

const modules = [
  {
    no: '01',
    name: 'Backtest',
    path: '/backtest',
    tag: '回測引擎',
    desc: '載入市場數據，套用技術 / 組合策略，秒級生成績效報告、權益曲線與交易分佈。',
    metric: 'P&L',
  },
  {
    no: '02',
    name: 'Optimize',
    path: '/optimize',
    tag: '參數優化',
    desc: '貝葉斯優化自動掃參，收斂到最佳風險調整後參數，輸出 WF + 蒙地卡羅穩健性報告。',
    metric: 'SHARPE',
  },
  {
    no: '03',
    name: 'History',
    path: '/history',
    tag: '回測歷史',
    desc: '所有已儲存回測記錄一覽，按 Sharpe / 日期排序，點擊還原該次結果進行檢視與匯出。',
    metric: 'ARCHIVE',
  },
  {
    no: '04',
    name: 'Strategies',
    path: '/strategies',
    tag: '策略管理',
    desc: '上傳你的 Python 策略（StrategyBase 抽象層），自帶未來函數檢測，一鍵跑回測或優化。',
    metric: 'PYTHON',
  },
];

/* ── Masthead: the desk opens with numbers, not slogans ── */
function DeskBoard({ loading, error, stats, rows }: ReturnType<typeof useDashboard>) {

  const today = useMemo(() => {
    const d = new Date();
    return {
      date: d.toLocaleDateString('zh-TW', { year: 'numeric', month: 'long', day: 'numeric' }),
      weekday: d.toLocaleDateString('zh-TW', { weekday: 'long' }),
    };
  }, []);

  const walk = useMemo(() => equityPath(Math.max(stats.total, 7)), [stats.total]);

  const cells: { label: string; value: string; accent?: 'success' | 'danger' | 'accent' }[] = [
    { label: '總回測數', value: loading ? '—' : String(stats.total) },
    {
      label: '平均 Sharpe',
      value: loading || stats.avgSharpe == null ? '—' : stats.avgSharpe.toFixed(3),
      accent: (stats.avgSharpe ?? 0) >= 0 ? 'success' : 'danger',
    },
    {
      label: '最佳 Sharpe',
      value: loading || !stats.bestRun ? '—' : Number(stats.bestRun.sharpe).toFixed(2),
      accent: 'success',
    },
    {
      label: '最差 Sharpe',
      value: loading || !stats.worstRun ? '—' : Number(stats.worstRun.sharpe).toFixed(2),
      accent: 'danger',
    },
  ];

  return (
    <section className="rise-in">
      {/* date line + live status */}
      <div className="flex flex-wrap items-center justify-between gap-3 font-mono text-[11px] uppercase tracking-[0.18em] text-textSecondary">
        <span>
          {today.date} · {today.weekday}
        </span>
        <span className="flex items-center gap-2">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping bg-success opacity-60" />
            <span className="relative inline-flex h-1.5 w-1.5 bg-success" />
          </span>
          Engine online
        </span>
      </div>

      {/* headline — left-aligned, the number is the hero */}
      <div className="mt-8 grid gap-10 lg:grid-cols-[1fr_auto] lg:items-end">
        <div>
          <h1 className="font-display text-4xl font-semibold leading-[1.2] tracking-tight md:text-6xl">
            在市場中
            <br />
            <span className="text-accent">持續賺取 P&L</span>
          </h1>
          <p className="mt-6 max-w-xl text-sm leading-relaxed text-textSecondary md:text-base">
            極簡、高性能的量化回測與優化平台。從策略構想到樣本外驗證，一套工具完成全部工作流。
            數據天賦 × 策略思維 × 高速執行。
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/backtest"
              className="group inline-flex items-center gap-2 bg-accent px-5 py-3 text-sm font-medium text-accentInk transition-colors hover:bg-accentStrong"
            >
              進入平台
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/history"
              className="inline-flex items-center gap-2 border border-border/60 px-5 py-3 text-sm font-medium text-text transition-colors hover:border-accent/50 hover:text-accent"
            >
              回測歷史
            </Link>
          </div>
        </div>

        {/* signature equity line — draws itself on load */}
        <div className="hidden md:block" aria-hidden>
          <svg width="320" height="120" viewBox="0 0 600 120" fill="none">
            <line x1="0" y1="119" x2="600" y2="119" stroke="rgb(var(--border))" strokeWidth="1" />
            <polyline
              points={walk.pts}
              stroke="rgb(var(--accent))"
              strokeWidth="2"
              className="pnl-draw"
              style={{ ['--line-len' as string]: walk.len }}
            />
          </svg>
          <p className="mt-2 text-right font-mono text-[10px] uppercase tracking-[0.18em] text-textSecondary">
            Equity · simulated walk
          </p>
        </div>
      </div>

      {/* ledger stats strip */}
      <div className="mt-12 metrics-grid grid grid-cols-2 gap-px lg:grid-cols-4">
        {cells.map((c, i) => (
          <div
            key={c.label}
            className="rise-in bg-surface p-5 metric-item"
            style={{ animationDelay: `${120 + i * 80}ms` }}
          >
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 bg-accent" />
              <span className="font-mono text-[11px] uppercase tracking-wider text-textSecondary">
                {c.label}
              </span>
            </div>
            <p
              className={`mt-3 font-mono text-3xl font-semibold tracking-tight ${
                c.accent === 'success'
                  ? 'text-success'
                  : c.accent === 'danger'
                    ? 'text-danger'
                    : c.accent === 'accent'
                      ? 'text-accent'
                      : 'text-text'
              }`}
            >
              {c.value}
            </p>
          </div>
        ))}
      </div>

      {error && (
        <p className="mt-4 font-mono text-xs text-danger">stats: {error}</p>
      )}
      {!loading && !error && rows.length === 0 && (
        <p className="mt-4 font-mono text-xs text-textSecondary">
          尚無回測紀錄 — 前往 Backtest 執行第一筆。
        </p>
      )}
    </section>
  );
}

/* ── Recent runs ledger ── */
function RecentRuns({ rows, loading, error }: Pick<ReturnType<typeof useDashboard>, 'rows' | 'loading' | 'error'>) {
  if (loading)
    return (
      <div className="flex justify-center py-10">
        <Spinner />
      </div>
    );
  if (error) return <EmptyState title="無法載入紀錄" description={error} />;
  if (rows.length === 0) return null;

  return (
    <section className="rise-in" style={{ animationDelay: '200ms' }}>
      <div className="flex items-end justify-between">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 bg-accent" />
          <h2 className="font-mono text-xs font-medium uppercase tracking-[0.18em] text-textSecondary">
            Recent runs
          </h2>
        </div>
        <Link
          href="/history"
          className="group inline-flex items-center gap-1 font-mono text-xs uppercase tracking-wider text-textSecondary transition-colors hover:text-accent"
        >
          全部紀錄
          <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
        </Link>
      </div>

      <div className="mt-4 divide-y divide-border/30 border-y border-border/40">
        {rows.slice(0, 8).map((r) => (
          <Link
            key={r.task_id}
            href={`/backtest?task=${r.task_id}`}
            className="ledger-row group flex items-center justify-between gap-4 px-3 py-3.5"
          >
            <div className="flex min-w-0 items-baseline gap-3">
              <span className="hidden shrink-0 font-mono text-[11px] text-textSecondary/70 sm:block">
                {r.created_at?.slice(0, 10)}
              </span>
              <span className="truncate font-medium text-text transition-colors group-hover:text-accent">
                {r.strategy ?? 'strategy'}
              </span>
              <span className="shrink-0 font-mono text-xs text-textSecondary">
                {r.symbol ?? '—'} · {r.timeframe ?? ''}
              </span>
            </div>
            <div className="flex shrink-0 items-center gap-4 font-mono text-sm">
              <span className="hidden text-textSecondary sm:block">{r.total_trades ?? 0} 筆</span>
              <span className={(r.sharpe ?? 0) >= 0 ? 'text-success' : 'text-danger'}>
                SR {Number(r.sharpe ?? 0).toFixed(2)}
              </span>
              {((r as any).return_pct) != null && (
                <span className={Number((r as any).return_pct) >= 0 ? 'text-success' : 'text-danger'}>
                  {Number((r as any).return_pct) >= 0 ? '+' : ''}{Number((r as any).return_pct).toFixed(1)}%
                </span>
              )}
              {((r as any).max_dd) != null && (
                <span className="text-textSecondary">
                  DD {Number((r as any).max_dd).toFixed(1)}%
                </span>
              )}
              <ArrowRight className="h-4 w-4 text-textSecondary transition-all group-hover:translate-x-0.5 group-hover:text-accent" />
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}

/* ── Module index — numbered ledger rows, not a card grid ── */
function ModuleIndex() {
  return (
    <section className="rise-in" style={{ animationDelay: '280ms' }}>
      <div className="flex items-end justify-between">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 bg-accent" />
          <h2 className="font-mono text-xs font-medium uppercase tracking-[0.18em] text-textSecondary">
            Workflows
          </h2>
        </div>
        <span className="font-mono text-xs text-textSecondary">04 modules</span>
      </div>

      <div className="mt-4 divide-y divide-border/30 border-y border-border/40">
        {modules.map((m) => (
          <Link
            key={m.no}
            href={m.path}
            className="ledger-row group grid grid-cols-[auto_1fr_auto] items-center gap-x-5 gap-y-1 px-3 py-5 md:grid-cols-[auto_220px_1fr_auto_auto]"
          >
            <span className="font-display text-2xl font-semibold text-accent/40 transition-colors group-hover:text-accent md:text-3xl">
              {m.no}
            </span>
            <div>
              <h3 className="font-display text-lg font-semibold tracking-tight transition-colors group-hover:text-accent">
                {m.name}
              </h3>
              <p className="font-mono text-[11px] uppercase tracking-wider text-accent/80">{m.tag}</p>
            </div>
            <p className="col-span-3 text-sm leading-relaxed text-textSecondary md:col-span-1">
              {m.desc}
            </p>
            <span className="hidden font-mono text-[10px] uppercase tracking-widest text-textSecondary md:block">
              {m.metric}
            </span>
            <ArrowRight className="hidden h-4 w-4 text-textSecondary transition-all group-hover:translate-x-0.5 group-hover:text-accent md:block" />
          </Link>
        ))}
      </div>
    </section>
  );
}

export default function Home() {
  const dash = useDashboard();
  return (
    <div className="mx-auto max-w-7xl space-y-20 px-4 pb-16 pt-12 md:px-6 md:pt-16">
      <ErrorBoundary>
        <DeskBoard {...dash} />
      </ErrorBoundary>

      <ErrorBoundary>
        <RecentRuns {...dash} />
      </ErrorBoundary>

      <ModuleIndex />

      {/* ── closing band — the discipline line, left-aligned ── */}
      <section className="rise-in border border-border/40 bg-surface px-8 py-12 md:px-12 md:py-16">
        <div className="accent-rule mb-8 w-24" />
        <h2 className="max-w-2xl font-display text-2xl font-semibold leading-tight tracking-tight md:text-3xl">
          紀律就是利潤，情緒就是成本。
        </h2>
        <p className="mt-4 max-w-xl text-sm text-textSecondary">
          從第一筆回測開始，建立你的系統化交易優勢。
        </p>
        <Link
          href="/backtest"
          className="group mt-8 inline-flex items-center gap-2 bg-accent px-5 py-3 text-sm font-medium text-accentInk transition-colors hover:bg-accentStrong"
        >
          開始回測
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </section>

      {/* version stamp */}
      <div className="mt-16 select-none text-center font-mono text-[11px] text-textSecondary/30">
        {APP_VERSION}
      </div>
    </div>
  );
}
