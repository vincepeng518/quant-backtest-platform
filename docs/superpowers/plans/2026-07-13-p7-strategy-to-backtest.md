# P7 One-Click Backtest from Strategy Library

> Sub-skill: ponytail (laziest path) + superpowers:executing-plans.

**Goal:** From the `/strategies` page, a user-uploaded strategy has a "跑回測" button that jumps to `/backtest?strategy=user_{id}` and preselects that strategy. No backend change.

**Evidence (already wired):**
- Backend registers user strategies as `user_{sid}` (strategy_service.py:48 `load_user_strategies()`, `_load_one` sets `attr.name = f"user_{sid}"`). So `get_strategy("user_{id}")` resolves.
- backtest/page.tsx already builds `userOptions` with value `user_${s.id}` (line 160-163) → backend-compatible.
- backtest/page.tsx already imports `useSearchParams` (line 36) and reads `task`.

## Changes
### A. backtest/page.tsx
In the templates-load effect (line 92-98), after `setTemplates`/`setUserStrategies`, read `searchParams.get('strategy')`. If present and equals a builtin `t.id` OR a `user_${id}` present in userStrategies, call `setSelectedStrategy(value)` and seed `paramValues` via `buildDefaults` (for builtin) — for user strategies params are unknown so just set selectedStrategy (params default empty is fine).

Concrete edit (replace the effect at 92-98):
```tsx
  useEffect(() => {
    api.getTemplates().then(setTemplates);
    api.listUserStrategies().then(setUserStrategies);
  }, []);

  // Preselect strategy from ?strategy= (e.g. user_xxxx) — P7
  useEffect(() => {
    const pref = searchParams.get('strategy');
    if (!pref) return;
    const isBuiltin = templates.some((t) => t.id === pref);
    const isUser = userStrategies.some((s) => `user_${s.id}` === pref);
    if (isBuiltin || isUser) {
      setSelectedStrategy(pref);
      if (isBuiltin) {
        const t = templates.find((x) => x.id === pref);
        if (t && Object.keys(paramValues).length === 0) setParamValues(buildDefaults(t));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templates, userStrategies]);
```

### B. strategies/page.tsx
1. Add imports: `import { useRouter } from 'next/navigation';`
2. Inside component: `const router = useRouter();`
3. In the user-strategy card (after the 刪除 button, line ~146), add:
```tsx
<button onClick={() => router.push(`/backtest?strategy=user_${s.id}`)} className="text-xs text-accent hover:underline transition-colors">跑回測</button>
```

## Verify
- `cd /root/Crypto-Backtesting-Lab/frontend && npm run build` → exit 0 (note: backtest page needs Suspense around useSearchParams — already wrapped per P3 history; if build complains, wrap in <Suspense>).
- Deploy + live:
  - `/strategies` 200
  - POST a test user strategy, note id, GET `/backtest?strategy=user_{id}` → 200, and confirm the strategy Select would preselect (can't see DOM easily; rely on build + code review + the fact value matches registry).
  - Cleanup: DELETE the test strategy.
