# P8 One-Click Optimize from Strategy Library

> ponytail + executing-plans. No backend change (optimize_service resolves `user_{id}` via get_strategy).

**Goal:** From `/strategies`, a user strategy has a "跑優化" button → `/optimize?strategy=user_{id}`, and the optimize page dynamically lists user strategies + preselects from `?strategy=`.

## A. optimize/page.tsx
1. Add imports: `useEffect`, `useState` (React already imported as default; add named `useEffect, useState`), `useSearchParams` from 'next/navigation', `Spinner` maybe not needed.
2. Replace `const STRATEGIES = [...]` (lines 16-22) with a state built in an effect:
```tsx
const [strategyOptions, setStrategyOptions] = useState<{label:string;value:string}[]>([
  { label: 'Moving Average Cross', value: 'ma_cross' },
  { label: 'RSI Reversion', value: 'rsi_reversion' },
  { label: 'Breakout', value: 'breakout' },
  { label: 'Pairs Trade', value: 'pairs' },
  { label: 'Stat Arb', value: 'stat_arb' },
]);
useEffect(() => {
  Promise.all([api.getTemplates(), api.listUserStrategies()])
    .then(([t, u]) => {
      const builtin = (t as any[]).map((x) => ({ label: x.name, value: x.id }));
      const user = (u as any[]).map((s) => ({ label: `我的：${s.name}`, value: `user_${s.id}` }));
      // merge: user first (so they show), then builtin not already present
      const seen = new Set([...user.map((o) => o.value), ...builtin.map((o) => o.value)]);
      const merged = [...user, ...builtin.filter((b) => !seen.has(b.value) || builtin.length === 0 ? true : !user.some((x) => x.value === b.value))];
      setStrategyOptions(merged);
    })
    .catch(() => {/* keep hardcoded fallback */});
}, []);
```
(Simplify: `const merged = [...user, ...builtin.filter(b => !user.some(u2 => u2.value === b.value))];`)

3. Preselect from `?strategy=`:
```tsx
const searchParams = useSearchParams();
useEffect(() => {
  const pref = searchParams.get('strategy');
  if (pref && strategyOptions.some((o) => o.value === pref)) {
    setStrategy(pref);
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [strategyOptions]);
```

4. Change Select at line 62: `options={STRATEGIES}` → `options={strategyOptions}`.

NOTE: `useSearchParams` requires a Suspense boundary in Next 14 build for static pages. The page is `'use client'` but Next still wants Suspense. P3 wrapped backtest page in Suspense. Check if optimize already wrapped; if build fails on useSearchParams, wrap the component return in `<Suspense fallback={<Spinner/>}>`.

## B. strategies/page.tsx
Add "跑優化" button next to "跑回測":
```tsx
<button onClick={() => router.push(`/optimize?strategy=user_${s.id}`)} className="text-xs text-accent hover:underline transition-colors">跑優化</button>
```

## Verify
- `cd /root/Crypto-Backtesting-Lab/frontend && npm run build` → exit 0.
- Deploy + live:
  - `/strategies` 200, `/optimize` 200, `/optimize?strategy=user_test` 200.
  - Upload test strategy, GET `/optimize?strategy=user_{id}` 200, cleanup DELETE.
