# P5 Completion Alerts (in-app toasts) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notify the trader when a backtest or optimization task finishes (completed or failed) via a global in-app toast — so they don't have to watch the page or manually poll.

**Architecture:** A standalone `useToastStore` (zustand) + a `<ToastViewport/>` mounted once in `RootLayout`. The existing `useBacktestStore` / `useOptimizeStore` call `useToastStore.getState().push()` when their `status` transitions to `completed` or `error`. No backend change, no bot token, no new API.

**Tech Stack:** Next.js 14 App Router, TypeScript, zustand, Tailwind (tokens: `bg-surface`, `border-border`, `text-accent`, `text-success`, `text-danger`, `text-text`).

## Global Constraints
- Impeccable design: borderless, whitespace, mono numbers, dark/light adaptive. Reuse existing tokens only.
- No backend change. No new API endpoint. No external services.
- Toast auto-dismisses after ~5s; manual close button. Stack vertically, max 3 visible.
- Branch: `master` (P1–P4 already merged). Commit per task. Build must stay green.
- POLLUTION GUARD: no writes to repo during verify; toasts are client-only UI.

---

### Task 1: Toast store + viewport component

**Files:**
- Create: `frontend/src/stores/useToastStore.ts`
- Create: `frontend/src/components/ui/Toast.tsx`

**Interfaces:**
- `useToastStore` → `{ toasts: ToastItem[]; push: (t: { title: string; message?: string; kind?: 'success'|'danger'|'info' }) => void; dismiss: (id: string) => void }`
- `ToastItem` = `{ id: string; title: string; message?: string; kind: 'success'|'danger'|'info' }`
- `ToastViewport` (default export of Toast.tsx) renders all toasts from the store, fixed bottom-right.

- [ ] **Step 1: Write the toast store**

```ts
'use client';

import { create } from 'zustand';

export type ToastKind = 'success' | 'danger' | 'info';

export interface ToastItem {
  id: string;
  title: string;
  message?: string;
  kind: ToastKind;
}

interface ToastStore {
  toasts: ToastItem[];
  push: (t: { title: string; message?: string; kind?: ToastKind }) => void;
  dismiss: (id: string) => void;
}

export const useToastStore = create<ToastStore>((set, get) => ({
  toasts: [],
  push: ({ title, message, kind = 'info' }) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const item: ToastItem = { id, title, message, kind };
    const next = [...get().toasts, item].slice(-3);
    set({ toasts: next });
    setTimeout(() => get().dismiss(id), 5000);
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}));
```

- [ ] **Step 2: Write the Toast viewport component**

```tsx
'use client';

import React from 'react';
import { useToastStore, ToastKind } from '@/stores/useToastStore';

const KIND_STYLE: Record<ToastKind, string> = {
  success: 'border-l-accent text-accent',
  danger: 'border-l-danger text-danger',
  info: 'border-l-textSecondary text-textSecondary',
};

export const ToastViewport: React.FC = () => {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-80 max-w-[calc(100vw-2rem)]">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`bg-surface border border-border/10 border-l-2 ${KIND_STYLE[t.kind]} rounded-md px-4 py-3 shadow-lg backdrop-blur-sm`}
          role="status"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex flex-col">
              <span className="text-sm font-semibold text-text">{t.title}</span>
              {t.message && <span className="text-xs text-textSecondary mt-0.5">{t.message}</span>}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              className="text-textSecondary hover:text-text transition-colors text-xs leading-none"
              aria-label="dismiss"
            >
              ✕
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};
```

- [ ] **Step 3: Type-check**

Run: `cd /root/Crypto-Backtesting-Lab/frontend && npx tsc --noEmit -p tsconfig.json`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/stores/useToastStore.ts frontend/src/components/ui/Toast.tsx
git commit -m "feat(toast): global toast store + viewport"
```

---

### Task 2: Mount ToastViewport in RootLayout

**Files:**
- Modify: `frontend/src/app/layout.tsx`

**Interfaces:**
- Consumes: `ToastViewport` from `@/components/ui/Toast`.

- [ ] **Step 1: Add import + render**

After `import { Header } from '@/components/layout/Header';`, add:
```tsx
import { ToastViewport } from '@/components/ui/Toast';
```
Inside the returned JSX, after `{children}` (inside the same wrapper div, before its closing tag), add:
```tsx
<ToastViewport />
```

- [ ] **Step 2: Build**

Run: `cd /root/Crypto-Backtesting-Lab/frontend && npm run build 2>&1 | tail -15`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/layout.tsx
git commit -m "feat(toast): mount ToastViewport in RootLayout"
```

---

### Task 3: Wire backtest completion into toast

**Files:**
- Modify: `frontend/src/stores/useBacktestStore.ts`

**Interfaces:**
- Consumes: `useToastStore` from `@/stores/useToastStore`.

- [ ] **Step 1: Add import**

At top of file: `import { useToastStore } from '@/stores/useToastStore';`

- [ ] **Step 2: Push toast on completion + error**

In `runBacktest`, at the `progressData.status === 'done'` branch (where it does `set({ status: 'completed', results });`), add BEFORE/AFTER the set:
```ts
useToastStore.getState().push({
  kind: 'success',
  title: '回測完成',
  message: `${config?.symbol ?? ''} · Sharpe ${(results as any)?.metrics?.sharpe_ratio?.toFixed(2) ?? '—'}`,
});
```
In the `progressData.status === 'error'` branch (where it does `set({ status: 'error', error: progressData.error });`), add:
```ts
useToastStore.getState().push({ kind: 'danger', title: '回測失敗', message: progressData.error ?? 'unknown' });
```
Also in the catch block that sets `status: 'error'` (polling/request failure), add a danger toast with `err.message`.

(Read the file to find the EXACT set() call sites and insert the push adjacent to each.)

- [ ] **Step 3: Build**

Run: `cd /root/Crypto-Backtesting-Lab/frontend && npm run build 2>&1 | tail -15`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/stores/useBacktestStore.ts
git commit -m "feat(toast): backtest completion + error alerts"
```

---

### Task 4: Wire optimize completion into toast

**Files:**
- Modify: `frontend/src/stores/useOptimizeStore.ts`

**Interfaces:**
- Consumes: `useToastStore` from `@/stores/useToastStore`.

- [ ] **Step 1: Read the file to find status transitions**

Run: `sed -n '1,120p' frontend/src/stores/useOptimizeStore.ts`
Identify the exact `set({ status: 'completed' ... })` and `set({ status: 'error' ... })` / catch sites.

- [ ] **Step 2: Add import + push at each transition**

At top: `import { useToastStore } from '@/stores/useToastStore';`
On completion: `useToastStore.getState().push({ kind: 'success', title: '優化完成', message: \`最佳 Sharpe ${bestSharpe?.toFixed(2) ?? '—'}\` });`
On error: `useToastStore.getState().push({ kind: 'danger', title: '優化失敗', message: errMsg });`

(Adapt message to the actual fields available in that store — read it first. Keep it minimal: title + 1 line message.)

- [ ] **Step 3: Build**

Run: `cd /root/Crypto-Backtesting-Lab/frontend && npm run build 2>&1 | tail -15`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/stores/useOptimizeStore.ts
git commit -m "feat(toast): optimize completion + error alerts"
```

---

### Task 5: Build + deploy + live verify

**Files:** none new.

- [ ] **Step 1: Final build**

Run: `cd /root/Crypto-Backtesting-Lab/frontend && npm run build 2>&1 | tail -15`
Expected: exit 0, `/` prerenders clean.

- [ ] **Step 2: Push + Vercel deploy + re-alias**

```bash
cd /root/Crypto-Backtesting-Lab
git push origin master
export VERCEL_TOKEN=$(grep VERCEL_TOKEN /root/.env | cut -d= -f2 | tr -d '"' | tr -d ' ')
URL=$(npx vercel --prod --yes --token "$VERCEL_TOKEN" 2>&1 | grep -oE "https://[a-z0-9-]+\.vercel\.app" | head -1)
npx vercel alias set "$URL" quant-backtest-platform-v2.vercel.app --token "$VERCEL_TOKEN"
```

- [ ] **Step 3: Live verify**

- `curl -s --max-time 20 https://quant-backtest-platform-v2.vercel.app/ -o /dev/null -w "%{http_code}"` → `200`
- Regression: `/backtest` `/optimize` `/data` `/history` `/analysis` all 200.
- Manual/code check: a completed backtest triggers a toast (cannot curl-trigger easily; confirm build + that the store push lines exist). Note: functional toast requires browser interaction — covered by build + code review.

- [ ] **Step 4: Done**
