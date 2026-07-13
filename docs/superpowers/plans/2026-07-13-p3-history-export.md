# P3 — Backtest 歷史記錄與結果匯出 Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

> Git: branch `p2-dataflow` is live on master. Create `p3-history-export` from current HEAD. Commit per task. Do NOT push until final verify.

## File Structure Changes
```
app/services/data_service.py          [EDIT] P3a-1  persist result to backtests/{task_id}.json via git_persist
app/api/routes/backtest.py            [EDIT] P3a-2  add /history; /results fallback to json file
frontend/src/app/history/page.tsx     [NEW]  P3a-4  history list + click→backtest
frontend/src/app/backtest/page.tsx    [EDIT] P3a-5  read ?task= query → load results; P3b export CSV btn
frontend/src/components/layout/Header.tsx [EDIT] P3a-6 add History nav link
```

No new npm deps. Railway GITHUB_TOKEN already set (git_persist will push).

## Global Constraints
- Reuse `git_persist` from `app.services.strategy_git` (signature `git_persist(files: list[str], message: str) -> tuple[bool,str]`).
- `backtests/` dir: create with `Path.mkdir(parents=True, exist_ok=True)` on first write.
- `/api/backtest/results/{task_id}` must fall back to reading `backtests/{task_id}.json` when in-memory store misses (so post-restart history items open).
- CSV export is client-side only (Blob + anchor download), no backend change.
- Build gate: `cd frontend && npm run build` exit 0.
- Verify on `https://quant-backtest-platform-v2.vercel.app/history` after deploy.
- POLLUTION GUARD: git_persist pushes to GitHub master — this is intended (same pattern as strategies). Verify `backtests/` JSON appears in GitHub repo after a backtest run.

## Task 1: persist backtest result to git
**File:** `app/services/data_service.py` (EDIT)
1. Add import near top: `from app.services.strategy_git import git_persist` and `from pathlib import Path` (if not present) and `import json`, `from datetime import datetime`.
2. In `_execute_backtest`, in the `try` branch after `store[task_id]["result"] = result`, add persistence:
```python
        # P3: persist result to git for history (survives restart)
        try:
            from app.services.strategy_git import git_persist
            import json as _json
            from datetime import datetime as _dt
            from pathlib import Path as _P
            _bd = _P(__file__).resolve().parents[2] / "backtests"
            _bd.mkdir(parents=True, exist_ok=True)
            _cfg = store[task_id].get("config", {})
            _payload = {
                "task_id": task_id,
                "status": "completed",
                "created_at": _dt.utcnow().isoformat(),
                "config": _cfg,
                "metrics": result.metrics.model_dump() if hasattr(result, "metrics") else {},
                "equity_curve": result.equity_curve,
                "trades": [t.model_dump() if hasattr(t, "model_dump") else t for t in result.trades],
            }
            _fp = _bd / f"{task_id}.json"
            _fp.write_text(_json.dumps(_payload, default=str, indent=2))
            ok, detail = git_persist([str(_fp)], f"feat(backtest): save {task_id}")
            if not ok:
                logger.warning("backtest persist skipped: %s", detail)
        except Exception as _e:
            logger.warning("backtest persist failed: %s", _e)
```
   NOTE: `store[task_id]["config"]` must exist. Check `run_backtest` in backtest_service stores config into `_backtest_tasks[task_id]` — if not, also store it there (in Task 1 companion edit: in `BacktestService.run`, after creating task, set `store[task_id]["config"] = config.model_dump()`). Verify by reading backtest_service.py first.
3. VERIFY: python import + run a quick local backtest (source=test) and confirm `backtests/{task_id}.json` created. (Use `python3 -c` with BacktestService; source test is offline.)
COMMIT: `git add app/services/data_service.py app/services/backtest_service.py && git commit -m "feat(backtest): persist result to git for history"`

## Task 2: history endpoint + results fallback
**File:** `app/api/routes/backtest.py` (EDIT)
1. Add import: `import json`, `from pathlib import Path`.
2. Add new route before `/status/{task_id}`:
```python
@router.get("/history")
async def list_history():
    bd = Path(__file__).resolve().parents[2] / "backtests"
    if not bd.exists():
        return []
    items = []
    for f in sorted(bd.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        m = d.get("metrics", {})
        cfg = d.get("config", {})
        items.append({
            "task_id": d.get("task_id"),
            "status": d.get("status"),
            "created_at": d.get("created_at"),
            "strategy": cfg.get("strategy_id") or cfg.get("template_id"),
            "symbol": cfg.get("symbol"),
            "timeframe": cfg.get("timeframe"),
            "sharpe": m.get("sharpe_ratio"),
            "total_trades": m.get("total_trades"),
        })
    return items
```
3. Modify `get_results` to fall back to file when in-memory misses:
```python
@router.get("/results/{task_id}", response_model=BacktestResultOut)
async def get_results(task_id: str):
    task = _backtest_tasks.get(task_id)
    if task and task.get("result") is not None:
        return task["result"]
    # fallback: read persisted json
    bd = Path(__file__).resolve().parents[2] / "backtests"
    fp = bd / f"{task_id}.json"
    if fp.exists():
        d = json.loads(fp.read_text())
        return BacktestResultOut(
            task_id=task_id,
            status=d.get("status", "completed"),
            metrics=d.get("metrics", {}),
            equity_curve=d.get("equity_curve", []),
            trades=d.get("trades", []),
        )
    raise HTTPException(status_code=404, detail="task not found")
```
   (Adjust field names to match BacktestResultOut + MetricsOut actual schema — read schemas.py.)
4. VERIFY: after a backtest run, `curl /api/backtest/history` returns non-empty; `curl /api/backtest/results/{task_id}` returns result.
COMMIT: `git add app/api/routes/backtest.py && git commit -m "feat(backtest): add history endpoint + file fallback for results"`

## Task 3: history page
**File:** `frontend/src/app/history/page.tsx` (NEW)
```tsx
'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { PageShell } from '@/components/layout/PageShell';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { api } from '@/lib/api';

interface HistoryItem {
  task_id: string;
  status: string;
  created_at: string;
  strategy: string;
  symbol: string;
  timeframe: string;
  sharpe: number;
  total_trades: number;
}

export default function HistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getBacktestHistory()
      .then(setItems)
      .catch((e) => setError(e?.message ?? 'failed to load history'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <PageShell
      eyebrow="History / records"
      title="回測歷史"
      subtitle="已儲存的回測運行記錄，點擊可還原該次結果進行檢視與匯出。"
    >
      <Card className="min-h-[300px]">
        {loading ? (
          <div className="flex justify-center py-12"><Spinner size="lg" /></div>
        ) : error ? (
          <p className="text-sm font-mono text-danger p-6">{error}</p>
        ) : items.length === 0 ? (
          <EmptyState title="No backtest records yet" description="Run a backtest to populate history." />
        ) : (
          <div className="divide-y divide-border/10">
            {items.map((it) => (
              <button
                key={it.task_id}
                onClick={() => router.push(`/backtest?task=${it.task_id}`)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface/50 text-left transition-colors"
              >
                <div>
                  <p className="text-sm font-mono text-text">{it.strategy ?? '—'} · {it.symbol ?? '—'} · {it.timeframe ?? '—'}</p>
                  <p className="text-xs text-textSecondary font-mono">{it.task_id} · {it.created_at?.slice(0, 19)?.replace('T', ' ')}</p>
                </div>
                <div className="text-right">
                  <p className={`text-sm font-mono ${it.sharpe != null && it.sharpe >= 0 ? 'text-success' : 'text-danger'}`}>
                    {it.sharpe != null ? it.sharpe.toFixed(3) : '—'}
                  </p>
                  <p className="text-xs text-textSecondary font-mono">{it.total_trades ?? 0} trades</p>
                </div>
              </button>
            ))}
          </div>
        )}
      </Card>
    </PageShell>
  );
}
```
VERIFY: tsc clean.
COMMIT: `git add frontend/src/app/history/page.tsx && git commit -m "feat(history): add backtest history page"`

## Task 4: api.getBacktestHistory
**File:** `frontend/src/lib/api.ts` (EDIT)
1. Add to `api` object (near getBacktestResults):
```ts
  getBacktestHistory: () => request<any[]>('/backtest/history'),
```
VERIFY: tsc clean.
COMMIT: `git add frontend/src/lib/api.ts && git commit -m "feat(api): add getBacktestHistory"`

## Task 5: backtest page — load ?task= + export CSV
**File:** `frontend/src/app/backtest/page.tsx` (EDIT)
1. Add imports: `import { useSearchParams } from 'next/navigation';` and `import { useBacktestStore } from '@/stores/useBacktestStore';` (if not already).
2. Inside component, add:
```ts
  const searchParams = useSearchParams();
  const taskParam = searchParams.get('task');
  useEffect(() => {
    if (taskParam) {
      api.getBacktestResults(taskParam).then((r) => {
        useBacktestStore.getState().set({ status: 'completed', results: r });
      }).catch(() => {});
    }
  }, [taskParam]);
```
   (If the store has no `set`, use the existing results setter; read useBacktestStore.ts to find the correct method — likely `setResults` or direct `set`.)
3. Add CSV export function (client-side):
```ts
  const exportCsv = () => {
    if (!results) return;
    const rows: string[] = [];
    const tradeCols = ['entry_time','exit_time','entry_price','exit_price','pnl','pnl_pct','size','side'];
    rows.push(['#', ...tradeCols].join(','));
    results.trades.forEach((t: any, i: number) => {
      rows.push([i + 1, ...tradeCols.map((c) => JSON.stringify(t[c] ?? ''))].join(','));
    });
    rows.push('');
    rows.push('equity_curve');
    results.equity_curve.forEach((v: number, i: number) => rows.push(`${i},${v}`));
    const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `backtest_${results.task_id ?? 'export'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };
```
4. Add an "Export CSV" button (variant ghost) near the results header / run bar, gated on `results` existing:
```tsx
  {results && <Button variant="ghost" onClick={exportCsv}>Export CSV</Button>}
```
VERIFY: `cd frontend && npm run build` exit 0.
COMMIT: `git add frontend/src/app/backtest/page.tsx && git commit -m "feat(backtest): load ?task= + export CSV button"`

## Task 6: nav History link
**File:** `frontend/src/components/layout/Header.tsx` (EDIT)
Add a History nav link after the existing links (copy exact className from a sibling Link):
```tsx
<Link href="/history" className="<EXACT_COPIED_CLASSNAME>">History</Link>
```
VERIFY: `npm run build` exit 0.
COMMIT: `git add frontend/src/components/layout/Header.tsx && git commit -m "feat(nav): add History link"`

## Task 7: build + deploy verify
1. `cd frontend && npm run build` → exit 0.
2. `git push -u origin p3-history-export`
3. `railway up --detach` (backend persists now; GITHUB_TOKEN set)
4. `export VERCEL_TOKEN=$(grep VERCEL_TOKEN /root/.env | cut -d= -f2 | tr -d '"' | tr -d ' '); npx vercel --prod --yes --token "$VERCEL_TOKEN"`
5. Re-alias: `npx vercel alias set <new-url> quant-backtest-platform-v2.vercel.app --token "$VERCEL_TOKEN"`
6. Verify live:
   - run a backtest via API (source=test) → confirm `backtests/{task_id}.json` created and pushed to GitHub (`gh api repos/vincepeng518/quant-backtest-platform/contents/backtests` or check git log).
   - `curl /api/backtest/history` non-empty.
   - `curl /api/backtest/results/{task_id}` returns result.
   - Browser `/history` lists; `/backtest?task={id}` loads.
Report build exit, deploy URL, history curl, github push confirmation.
