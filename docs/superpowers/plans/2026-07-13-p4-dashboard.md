# P4 Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the static landing page (`/`) into a live dashboard that pulls recent backtest runs from `/api/backtest/history` and shows aggregate stats + a recent-runs table, matching the existing impeccable design system.

**Architecture:** Client component on `/` fetches `api.getBacktestHistory()` on mount, derives summary stats (total runs, avg sharpe, best/worst run) in the page, and renders them via the existing `MetricsCard`, `Spinner`, and `EmptyState` components. No new backend endpoint needed — reuses P3's `/backtest/history`.

**Tech Stack:** Next.js 14 App Router, TypeScript, Tailwind (tokens: `bg-surface`, `border-border`, `text-accent`, `text-success`, `text-danger`, `text-textSecondary`), existing `MetricsCard` / `Spinner` / `EmptyState`.

## Global Constraints
- Impeccable design: borderless, whitespace, mono numbers, dark/light adaptive (use existing tokens only).
- No new backend code. Reuse `GET /api/backtest/history` (returns `Array<{task_id, status, created_at, strategy, symbol, timeframe, sharpe, total_trades}>`).
- `metrics` from history are top-level: `sharpe` (number|null), `total_trades` (number|null). `strategy` may be null.
- Frequency: commit per task. Frontend build must stay green (`npm run build` exit 0).
- Multi-user/login is OUT OF SCOPE for P4 (deferred — solo SaaS). Do not add auth.
- POLLUTION GUARD: do NOT call the run endpoint from tests; the dashboard only GETs history. No writes to repo during verif.

---

### Task 1: Define dashboard types + data hook

**Files:**
- Create: `frontend/src/lib/dashboard.ts`

**Interfaces:**
- Produces: `HistoryRow` type (matches `/backtest/history` item), `useDashboard()` hook returning `{ rows, loading, error, stats }`.
- `stats` shape: `{ total, avgSharpe, bestRun, worstRun }` where best/worst are `HistoryRow | null`.

- [ ] **Step 1: Write the hook file**

```ts
'use client';

import { useEffect, useState } from 'react';
import { api } from './api';

export interface HistoryRow {
  task_id: string;
  status: string;
  created_at: string;
  strategy: string | null;
  symbol: string | null;
  timeframe: string | null;
  sharpe: number | null;
  total_trades: number | null;
}

export interface DashboardStats {
  total: number;
  avgSharpe: number | null;
  bestRun: HistoryRow | null;
  worstRun: HistoryRow | null;
}

function computeStats(rows: HistoryRow[]): DashboardStats {
  const withSharpe = rows.filter((r) => typeof r.sharpe === 'number');
  if (withSharpe.length === 0) {
    return { total: rows.length, avgSharpe: null, bestRun: null, worstRun: null };
  }
  const sorted = [...withSharpe].sort((a, b) => (b.sharpe as number) - (a.sharpe as number));
  const avg = withSharpe.reduce((s, r) => s + (r.sharpe as number), 0) / withSharpe.length;
  return {
    total: rows.length,
    avgSharpe: Math.round(avg * 1000) / 1000,
    bestRun: sorted[0],
    worstRun: sorted[sorted.length - 1],
  };
}

export function useDashboard() {
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.getBacktestHistory()
      .then((data: HistoryRow[]) => {
        if (!alive) return;
        setRows(data);
        setLoading(false);
      })
      .catch((e) => {
        if (!alive) return;
        setError(String(e?.message ?? e));
        setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  return { rows, loading, error, stats: computeStats(rows) };
}
```

- [ ] **Step 2: Type-check**

Run: `cd /root/Crypto-Backtesting-Lab/frontend && npx tsc --noEmit -p tsconfig.json`
Expected: exit 0 (no new errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/dashboard.ts
git commit -m "feat(dashboard): add types + useDashboard hook"
```

---

### Task 2: Stats summary strip (MetricsCard)

**Files:**
- Modify: `frontend/src/app/page.tsx` (add stats strip above modules, after hero or replacing capabilities block)

**Interfaces:**
- Consumes: `useDashboard()` from `frontend/src/lib/dashboard.ts` → `{ rows, loading, error, stats }`.
- Consumes: `MetricsCard` from `@/components/ui/MetricsCard`.
- Consumes: `Spinner` from `@/components/ui/Spinner`, `EmptyState` from `@/components/ui/EmptyState`.

- [ ] **Step 1: Add imports to page.tsx**

After the existing `import React from 'react';` line, add:

```ts
'use client';

import React, { useEffect } from 'react';
import Link from 'next/link';
import { Activity, Sliders, TrendingUp, ArrowRight, Database, Cpu, Gauge } from 'lucide-react';
import { MetricsCard } from '@/components/ui/MetricsCard';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { useDashboard } from '@/lib/dashboard';
```

(NOTE: page.tsx already has `'use client';` and the react/lucide imports — do NOT duplicate. Just add the `MetricsCard`, `Spinner`, `EmptyState`, `useDashboard` imports and `useEffect` to the existing react import if missing.)

- [ ] **Step 2: Add a `StatsStrip` component inside page.tsx (before `export default function Home`)**

```tsx
function StatsStrip() {
  const { loading, error, stats } = useDashboard();
  if (loading) return <Spinner />;
  if (error) return <EmptyState title="無法載入統計" message={error} />;
  const items = [
    { label: '總回測數', value: stats.total },
    { label: '平均 Sharpe', value: stats.avgSharpe ?? '—', accent: (stats.avgSharpe ?? 0) >= 0 ? 'success' : 'danger' },
    { label: '最佳 Sharpe', value: stats.bestRun ? stats.bestRun.sharpe?.toFixed(2) : '—', accent: 'success' },
    { label: '最差 Sharpe', value: stats.worstRun ? stats.worstRun.sharpe?.toFixed(2) : '—', accent: 'danger' },
  ] as const;
  return <MetricsCard items={items as unknown as { label: string; value: string | number; accent?: 'success' | 'danger' }[]} />;
}
```

- [ ] **Step 3: Render `<StatsStrip />` in the Home component**

Insert `<StatsStrip />` between the Hero `</section>` and the modules section (or directly replace the static `capabilities` block). Keep it borderless/whitespace per design.

- [ ] **Step 4: Build**

Run: `cd /root/Crypto-Backtesting-Lab/frontend && npm run build 2>&1 | tail -15`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/page.tsx
git commit -m "feat(dashboard): live stats strip via MetricsCard"
```

---

### Task 3: Recent runs table

**Files:**
- Modify: `frontend/src/app/page.tsx` (add `RecentRuns` component)

**Interfaces:**
- Consumes: `useDashboard()` → `{ rows }`.
- Consumes: `Spinner`, `EmptyState`.

- [ ] **Step 1: Add `RecentRuns` component (before `export default function Home`)**

```tsx
function RecentRuns() {
  const { rows, loading, error } = useDashboard();
  if (loading) return <Spinner />;
  if (error) return <EmptyState title="無法載入紀錄" message={error} />;
  if (rows.length === 0) {
    return <EmptyState title="尚無回測紀錄" message="前往 Backtest 執行第一筆回測" />;
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
                SR {(r.sharpe ?? 0).toFixed(2)}
              </span>
              <ArrowRight className="w-4 h-4 text-textSecondary group-hover:text-accent transition-colors" />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Render `<RecentRuns />` in Home (after StatsStrip, before or after modules)**

Place `<RecentRuns />` in its own `<section>` below the stats strip.

- [ ] **Step 3: Build**

Run: `cd /root/Crypto-Backtesting-Lab/frontend && npm run build 2>&1 | tail -15`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/page.tsx
git commit -m "feat(dashboard): recent runs table linking to ?task="
```

---

### Task 4: Build + deploy + live verify

**Files:**
- None new; deploys frontend only.

- [ ] **Step 1: Final build**

Run: `cd /root/Crypto-Backtesting-Lab/frontend && npm run build 2>&1 | tail -15`
Expected: exit 0, `/` prerenders clean.

- [ ] **Step 2: Push + Vercel deploy**

```bash
cd /root/Crypto-Backtesting-Lab
git push origin master
export VERCEL_TOKEN=$(grep VERCEL_TOKEN /root/.env | cut -d= -f2 | tr -d '"' | tr -d ' ')
npx vercel --prod --yes --token "$VERCEL_TOKEN"
npx vercel alias set <new-deploy-url> quant-backtest-platform-v2.vercel.app --token "$VERCEL_TOKEN"
```

- [ ] **Step 3: Live verify**

- `curl -s --max-time 20 https://quant-backtest-platform-v2.vercel.app/ -o /dev/null -w "%{http_code}"` → `200`
- `curl -s --max-time 25 https://quant-backtest-platform-v2.vercel.app/api/backtest/history` → returns JSON array (powers the dashboard)
- Confirm `/backtest?task=<id>` still loads results (P3 intact).
- Confirm no regression: `/data`, `/optimize`, `/history` still 200.

- [ ] **Step 4: Commit deploy verification note (no code change) — skip if clean**
