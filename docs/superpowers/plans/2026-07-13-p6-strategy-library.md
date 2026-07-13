# P6 Strategy Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/strategies` page that browses built-in strategy templates + the user's uploaded strategies, and lets the user upload a new Python strategy (reusing the existing backend endpoints). No new backend code.

**Architecture:** A client page `/strategies` fetches `api.getTemplates()` (built-in) and `api.listUserStrategies()` (user). An upload modal POSTs `api.uploadStrategy(payload)`. Delete calls `api.deleteStrategy(id)`. Uses existing `Spinner`, `EmptyState`, `MetricsCard`, `ToastViewport` (via `useToastStore`). Nav link added to Header (P2 pattern).

**Tech Stack:** Next.js 14 App Router, TypeScript, zustand (toast), Tailwind tokens (bg-surface, border-border, text-accent, text-success, text-danger, text-textSecondary).

## Global Constraints
- No backend change. Reuse: `GET /api/strategy/templates`, `GET /api/strategy/user`, `POST /api/strategy/upload`, `DELETE /api/strategy/user/{id}`, `PUT /api/strategy/user/{id}`.
- Design: impeccable, borderless, whitespace, mono numbers, dark/light adaptive. Reuse tokens only.
- Branch: `master` (P1–P5 merged). Commit per task. Build must stay green.
- POLLUTION GUARD: do NOT call upload in tests against prod; verification is build + code review + a real browser-free curl of `/api/strategy/templates` only (GET, no write).
- NOTE: frontend `UserStrategy` type (`frontend/src/types/api.ts`) lacks `status`/`error`/`filename`/`created_at:string` that the backend `UserStrategyMeta` returns. Define a local type in the page: `{ id, name, description, category, filename?, created_at?, status?, error?, params_space? }` OR use `any[]` for the user list to avoid type mismatch. Prefer a local `UserStrategyMeta` interface in the page file.

---

### Task 1: Strategy Library page (browse + upload + delete)

**Files:**
- Create: `frontend/src/app/strategies/page.tsx`

**Interfaces:**
- Consumes: `api.getTemplates()` → `StrategyTemplate[]` (`{id, name, description, category, params: StrategyParam[]}`); `api.listUserStrategies()` → array of user metas; `api.uploadStrategy(payload: StrategyPayload)` → `UserStrategy`; `api.deleteStrategy(id)` → `{status}`.
- Consumes: `useToastStore` (`push`), `Spinner`, `EmptyState`.
- `StrategyPayload` = `{ name: string; description: string; category: string; code: string }`.

- [ ] **Step 1: Write the page**

```tsx
'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { useToastStore } from '@/stores/useToastStore';

interface UserMeta {
  id: string;
  name: string;
  description: string;
  category: string;
  filename?: string;
  created_at?: string;
  status?: string;
  error?: string | null;
  params_space?: Record<string, unknown>;
}

const SAMPLE = `from app.engine.strategy_base import StrategyBase

class MyStrategy(StrategyBase):
    description = "My custom strategy"
    category = "custom"

    def get_params_space(self):
        return {"fast": (5, 50, 1), "slow": (20, 200, 1)}

    def generate_signals(self, df):
        fast = df["close"].rolling(int(self.params["fast"])).mean()
        slow = df["close"].rolling(int(self.params["slow"])).mean()
        return (fast > slow).astype(int).diff().fillna(0)
`;

export default function StrategiesPage() {
  const [templates, setTemplates] = useState<any[]>([]);
  const [user, setUser] = useState<UserMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [showUpload, setShowUpload] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', code: SAMPLE });
  const push = useToastStore((s) => s.push);

  const load = () => {
    Promise.all([api.getTemplates(), api.listUserStrategies()])
      .then(([t, u]) => {
        setTemplates(t as any[]);
        setUser(u as unknown as UserMeta[]);
        setLoading(false);
      })
      .catch((e) => {
        push({ kind: 'danger', title: '載入失敗', message: String(e?.message ?? e) });
        setLoading(false);
      });
  };

  useEffect(load, []);

  const submit = async () => {
    if (!form.name.trim() || !form.code.trim()) {
      push({ kind: 'danger', title: '請填寫名稱與代碼' });
      return;
    }
    try {
      await api.uploadStrategy({ name: form.name, description: form.description, category: 'custom', code: form.code });
      push({ kind: 'success', title: '策略已上傳', message: form.name });
      setShowUpload(false);
      setForm({ name: '', description: '', code: SAMPLE });
      load();
    } catch (e: any) {
      push({ kind: 'danger', title: '上傳失敗', message: e?.message ?? String(e) });
    }
  };

  const remove = async (id: string) => {
    try {
      await api.deleteStrategy(id);
      push({ kind: 'success', title: '已刪除策略' });
      load();
    } catch (e: any) {
      push({ kind: 'danger', title: '刪除失敗', message: e?.message ?? String(e) });
    }
  };

  if (loading) return <Spinner />;

  return (
    <div className="space-y-12 pb-12">
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-text">內建策略模板</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {templates.map((t) => (
            <div key={t.id} className="bg-surface border border-border/10 rounded-lg p-5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-text">{t.name}</span>
                <span className="text-xs text-textSecondary uppercase">{t.category}</span>
              </div>
              <p className="text-sm text-textSecondary line-clamp-2">{t.description}</p>
              <span className="text-xs font-mono text-accent">{t.params?.length ?? 0} params</span>
            </div>
          ))}
          {templates.length === 0 && <EmptyState title="無內建模板" />}
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-text">我的策略</h2>
          <button onClick={() => setShowUpload(true)} className="text-sm text-accent hover:underline">+ 上傳策略</button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {user.map((s) => (
            <div key={s.id} className="bg-surface border border-border/10 rounded-lg p-5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-text">{s.name}</span>
                <span className={`text-xs ${s.status === 'error' ? 'text-danger' : 'text-success'}`}>{s.status ?? 'registered'}</span>
              </div>
              <p className="text-sm text-textSecondary line-clamp-2">{s.description || s.filename}</p>
              {s.error && <p className="text-xs text-danger font-mono">{s.error}</p>}
              <button onClick={() => remove(s.id)} className="text-xs text-textSecondary hover:text-danger transition-colors">刪除</button>
            </div>
          ))}
          {user.length === 0 && <EmptyState title="尚無上傳策略" message="點擊右上角上傳你的 Python 策略" />}
        </div>
      </section>

      {showUpload && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setShowUpload(false)}>
          <div className="w-full max-w-2xl bg-surface border border-border/10 rounded-xl p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-semibold text-text">上傳策略</h3>
            <input
              className="w-full bg-background border border-border/10 rounded-md px-3 py-2 text-sm text-text"
              placeholder="策略名稱"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <input
              className="w-full bg-background border border-border/10 rounded-md px-3 py-2 text-sm text-text"
              placeholder="描述（選填）"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
            <textarea
              className="w-full h-72 bg-background border border-border/10 rounded-md px-3 py-2 text-xs font-mono text-text"
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowUpload(false)} className="text-sm text-textSecondary px-4 py-2">取消</button>
              <button onClick={submit} className="text-sm text-accent border border-accent/30 rounded-md px-4 py-2 hover:bg-accent/10 transition-colors">上傳</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Build**

Run: `cd /root/Crypto-Backtesting-Lab/frontend && npm run build 2>&1 | tail -20`
Expected: exit 0. (Note: `line-clamp-2` requires Tailwind line-clamp plugin OR is built-in in Tailwind v3.3+. If build errors on `line-clamp-2`, remove those classes — they are cosmetic.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/strategies/page.tsx
git commit -m "feat(strategies): strategy library page (browse + upload + delete)"
```

---

### Task 2: Nav link in Header

**Files:**
- Modify: `frontend/src/components/layout/Header.tsx`

- [ ] **Step 1: Add Strategies nav link**

Read Header.tsx to find the nav link list (where `<Link href="/backtest">`, `/optimize`, `/analysis`, `/data`, `/history` appear). Copy the EXACT className from one sibling link, then add:
```tsx
<Link href="/strategies" className="<EXACT_COPIED_CLASSNAME>">Strategies</Link>
```
Place it logically (e.g. after `/history` or after `/backtest`).

- [ ] **Step 2: Build**

Run: `cd /root/Crypto-Backtesting-Lab/frontend && npm run build 2>&1 | tail -15`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/layout/Header.tsx
git commit -m "feat(nav): add Strategies link"
```

---

### Task 3: Build + deploy + live verify

**Files:** none new.

- [ ] **Step 1: Final build**

Run: `cd /root/Crypto-Backtesting-Lab/frontend && npm run build 2>&1 | tail -15`
Expected: exit 0.

- [ ] **Step 2: Push + Vercel deploy + re-alias**

```bash
cd /root/Crypto-Backtesting-Lab
git push origin master
export VERCEL_TOKEN=$(grep VERCEL_TOKEN /root/.env | cut -d= -f2 | tr -d '"' | tr -d ' ')
URL=$(npx vercel --prod --yes --token "$VERCEL_TOKEN" 2>&1 | grep -oE "https://[a-z0-9-]+\.vercel\.app" | head -1)
npx vercel alias set "$URL" quant-backtest-platform-v2.vercel.app --token "$VERCEL_TOKEN"
```

- [ ] **Step 3: Live verify**

- `curl -s --max-time 20 https://quant-backtest-platform-v2.vercel.app/strategies -o /dev/null -w "%{http_code}"` → `200`
- `curl -s --max-time 25 https://quant-backtest-platform-v2.vercel.app/api/strategy/templates -o /dev/null -w "%{http_code}"` → `200` (powers the page)
- `curl -s --max-time 25 https://quant-backtest-platform-v2.vercel.app/api/strategy/user -o /dev/null -w "%{http_code}"` → `200`
- Regression: `/` `/backtest` `/optimize` `/data` `/history` `/analysis` all 200.
- (Upload flow is browser-interactive; covered by build + code review. Optionally POST a test strategy then DELETE it to confirm round-trip, then clean up.)

- [ ] **Step 4: Done**
