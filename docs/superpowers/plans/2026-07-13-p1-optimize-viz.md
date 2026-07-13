# P1 — 优化页完整化与结果可视化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 optimize 页从 stub 提升为完整功能页（多参数网格、策略/市场选择、Heatmap/条形图/收敛曲线可视化），并改后端 optimize 返回完整 2D grid 以支持热力图。

**Architecture:** 后端 `optimize_service._execute` 在 2 参数 range 时构建 `grid` matrix 并写入 `OptimizeResultOut`；前端 store 改用统一 `api.ts`，optimize 页重构为动态多参数配置 + 结果可视化（手写 SVG 组件，不引新库）。

**Tech Stack:** FastAPI (backend), Next.js 14 App Router + TypeScript (frontend), lightweight-charts (收敛曲线), 手写 SVG (Heatmap/条形图), zustand (store), Railway (backend deploy), Vercel (frontend deploy).

## Global Constraints
- 后端 `OptimizeResultOut` 新增 `grid` 字段，`trials[:10]` 保留兼容，不破坏现有前端。
- 前端图表组件用手写 SVG（ponytail：不引 recharts/d3 等新依赖）；收敛曲线复用 lightweight-charts。
- 所有 fetch 走 `frontend/src/lib/api.ts` 统一 client（BASE_URL = NEXT_PUBLIC_API_URL || '/api'）。
- 风格：borderless, whitespace, mono numbers, dark/light adaptive（premium minimal）。
- 后端改动需重部署 Railway；前端改动需重部署 Vercel。
- Pollution guard: 测试创建的用户策略/优化任务必须清理，不要污染生产 repo 或 Railway 服务。

---

## File Structure

### Backend (modify)
- `app/models/schemas.py` — `OptimizeResultOut` 增加 `grid: dict | None = None`
- `app/services/optimize_service.py` — `_execute` 构建 `grid` matrix（2 参数时）；`trials` 保留前 10

### Frontend (create + modify)
- `frontend/src/types/api.ts` — 增加 `OptimizeGrid`, `OptimizeResult` 接口
- `frontend/src/lib/api.ts` — 增加 `runOptimize`, `getOptimizeResults`, `applyBestParams`
- `frontend/src/stores/useOptimizeStore.ts` — 重构：统一 api client + 多参数/多策略/市场数据 state
- `frontend/src/components/charts/Heatmap.tsx` — 新建：2D 参数空间热力图（SVG）
- `frontend/src/components/charts/ParamImportanceBar.tsx` — 新建：每参数 score 分布条形图（SVG）
- `frontend/src/components/charts/ConvergenceChart.tsx` — 新建：best score over trials 收敛曲线（lightweight-charts）
- `frontend/src/app/optimize/page.tsx` — 重构：动态多参数配置 + 结果可视化

---

### Task 1: 后端 schema 增加 grid 字段

**Files:**
- Modify: `app/models/schemas.py:152-156` (`OptimizeResultOut`)

**Interfaces:**
- Consumes: 无
- Produces: `OptimizeResultOut.grid: dict | None` 字段，供 Task 2 填充

- [ ] **Step 1: 修改 OptimizeResultOut**
```python
class OptimizeResultOut(BaseModel):
    task_id: str
    status: str = "completed"
    best_params: dict[str, Any] = {}
    best_score: float = 0.0
    trials: list[dict] = []
    grid: dict | None = None  # 2D grid matrix，仅当 param_space 恰为 2 个 range 参数时填充
```

- [ ] **Step 2: Commit**
```bash
git add app/models/schemas.py
git commit -m "feat(optimize): add grid field to OptimizeResultOut"
```

---

### Task 2: 后端 optimize_service 构建 grid matrix

**Files:**
- Modify: `app/services/optimize_service.py:48-70` (`_execute` 中 param_space 构建与结果写入)

**Interfaces:**
- Consumes: `OptimizeResultOut.grid`（Task 1）
- Produces: `_optimize_tasks[task_id]` 含 `grid` 键（2 参数时为 dict，否则 None）

- [ ] **Step 1: 修改 _execute 中 param_space 与结果写入逻辑**
将现有：
```python
            param_space = {}
            for p in config.get("param_space", []):
                param_space[p["name"]] = {
                    "type": "range",
                    "min": p["min"],
                    "max": p["max"],
                    "step": p.get("step", 1),
                }

            opt = Optimizer(bt, metric="sharpe_ratio")
            if config.get("algorithm") == "bayesian":
                results = opt.bayesian_optimization(param_space, n_iterations=config.get("max_trials", 30))
            elif config.get("algorithm") == "genetic":
                results = opt.genetic_algorithm(param_space)
            else:
                results = opt.grid_search(param_space)

            _optimize_tasks[task_id] = {
                "status": "completed",
                "best_params": results[0]["params"] if results else {},
                "best_score": results[0]["score"] if results else 0.0,
                "trials": [{"params": r["params"], "score": r["score"]} for r in results[:10]],
            }
```
替换为：
```python
            param_space = {}
            raw_ranges = []
            for p in config.get("param_space", []):
                param_space[p["name"]] = {
                    "type": "range",
                    "min": p["min"],
                    "max": p["max"],
                    "step": p.get("step", 1),
                }
                raw_ranges.append(p)

            opt = Optimizer(bt, metric="sharpe_ratio")
            if config.get("algorithm") == "bayesian":
                results = opt.bayesian_optimization(param_space, n_iterations=config.get("max_trials", 30))
            elif config.get("algorithm") == "genetic":
                results = opt.genetic_algorithm(param_space)
            else:
                results = opt.grid_search(param_space)

            # Build 2D grid matrix only when exactly 2 range params
            grid = None
            if len(raw_ranges) == 2:
                px, py = raw_ranges[0]["name"], raw_ranges[1]["name"]
                import numpy as np
                x_vals = list(np.arange(raw_ranges[0]["min"], raw_ranges[0]["max"] + raw_ranges[0]["step"], raw_ranges[0]["step"]))
                y_vals = list(np.arange(raw_ranges[1]["min"], raw_ranges[1]["max"] + raw_ranges[1]["step"], raw_ranges[1]["step"]))
                score_map = {}
                for r in results:
                    score_map[(r["params"].get(px), r["params"].get(py))] = r["score"]
                matrix = []
                for yv in y_vals:
                    row = []
                    for xv in x_vals:
                        row.append(score_map.get((xv, yv), None))
                    matrix.append(row)
                grid = {
                    "param_x": px,
                    "param_y": py,
                    "x_values": [float(v) for v in x_vals],
                    "y_values": [float(v) for v in y_vals],
                    "scores": matrix,
                }

            _optimize_tasks[task_id] = {
                "status": "completed",
                "best_params": results[0]["params"] if results else {},
                "best_score": results[0]["score"] if results else 0.0,
                "trials": [{"params": r["params"], "score": r["score"]} for r in results[:10]],
                "grid": grid,
            }
```

- [ ] **Step 2: 本地验证 grid 构建**
```bash
cd /root/Crypto-Backtesting-Lab
python3 -c "
from app.services.optimize_service import OptimizeService
import asyncio
svc = OptimizeService()
async def t():
    cfg = {'strategy_id':'ma_cross','symbol':'BTC/USDT','timeframe':'1h','source':'test','param_space':[{'name':'fast_period','min':5,'max':15,'step':5},{'name':'slow_period','min':20,'max':40,'step':10}]}
    r = await svc.run(cfg)
    tid = r['task_id']
    import time; time.sleep(3)
    res = svc.get_results(tid)
    print('grid:', res.get('grid') is not None)
    if res.get('grid'):
        print('x:', res['grid']['x_values'], 'y:', res['grid']['y_values'])
        print('matrix rows:', len(res['grid']['scores']), 'cols:', len(res['grid']['scores'][0]))
t()
"
```
Expected: `grid: True`, x_values=[5.0,10.0,15.0], y_values=[20.0,30.0,40.0], matrix 3x3.

- [ ] **Step 3: Commit**
```bash
git add app/services/optimize_service.py
git commit -m "feat(optimize): build 2D grid matrix for heatmap"
```

---

### Task 3: 前端类型增加 OptimizeGrid / OptimizeResult

**Files:**
- Modify: `frontend/src/types/api.ts` (在文件末尾追加)

**Interfaces:**
- Consumes: 无
- Produces: `OptimizeGrid`, `OptimizeResult` 接口，供 Task 4/5/6/7 使用

- [ ] **Step 1: 追加类型定义**
```ts
export interface OptimizeGrid {
  param_x: string;
  param_y: string;
  x_values: number[];
  y_values: number[];
  scores: (number | null)[][];
}

export interface OptimizeResult {
  task_id: string;
  status: string;
  best_params: Record<string, any>;
  best_score: number;
  trials: { params: Record<string, any>; score: number }[];
  grid: OptimizeGrid | null;
}
```

- [ ] **Step 2: Commit**
```bash
git add frontend/src/types/api.ts
git commit -m "feat(optimize): add OptimizeGrid/OptimizeResult types"
```

---

### Task 4: api.ts 增加 optimize 方法

**Files:**
- Modify: `frontend/src/lib/api.ts:36-79` (在 `api` 对象内追加)

**Interfaces:**
- Consumes: `OptimizeResult` 类型（Task 3）
- Produces: `api.runOptimize`, `api.getOptimizeResults`, `api.applyBestParams`

- [ ] **Step 1: 在 api 对象内追加方法（在 getAnalysisResults 之后）**
```ts
  runOptimize: (config: any) =>
    request<{ task_id: string }>('/optimize/run', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  getOptimizeResults: (taskId: string) =>
    request<OptimizeResult>(`/optimize/results/${taskId}`),
  applyBestParams: () =>
    request<{ applied: boolean }>('/optimize/best-params', {
      method: 'POST',
    }),
```

- [ ] **Step 2: 确认 import 含 OptimizeResult**
检查 `frontend/src/lib/api.ts` 顶部 import 块（第 1-8 行），确认已导入 `OptimizeResult`。若无，在 `import {` 块中加入 `OptimizeResult,`：
```ts
import {
  BacktestConfig,
  BacktestResult,
  StrategyPayload,
  StrategyTemplate,
  UserStrategy,
  AnalysisResult,
  OptimizeResult,
} from '@/types/api';
```

- [ ] **Step 3: Commit**
```bash
git add frontend/src/lib/api.ts
git commit -m "feat(optimize): add optimize api methods"

---

### Task 5: useOptimizeStore 重构

**Files:**
- Modify: `frontend/src/stores/useOptimizeStore.ts` (整文件重写)

**Interfaces:**
- Consumes: `api.runOptimize`, `api.getOptimizeResults`, `api.applyBestParams` (Task 4)
- Produces: store 暴露 `status`, `progress`, `bestParams`, `bestScore`, `grid`, `trials`, `strategyId`, `paramSpace`, `symbol`, `timeframe`, `source`, `setStrategy`, `setMarket`, `addParam`, `updateParam`, `removeParam`, `runOptimization`, `reset`

- [ ] **Step 1: 重写 store 文件**
```ts
import { create } from 'zustand';
import api from '@/lib/api';

export interface ParamRangeUI {
  id: string;
  name: string;
  min: number;
  max: number;
  step: number;
}

interface OptimizeStore {
  status: 'idle' | 'running' | 'completed' | 'error';
  progress: number;
  error: string | null;
  bestParams: Record<string, any> | null;
  bestScore: number | null;
  grid: any | null;
  trials: { params: Record<string, any>; score: number }[];
  strategyId: string;
  symbol: string;
  timeframe: string;
  source: string;
  paramSpace: ParamRangeUI[];
  setStrategy: (id: string) => void;
  setMarket: (m: { symbol: string; timeframe: string; source: string }) => void;
  addParam: (name: string) => void;
  updateParam: (id: string, patch: Partial<ParamRangeUI>) => void;
  removeParam: (id: string) => void;
  runOptimization: () => Promise<void>;
  reset: () => void;
}

const uid = () => Math.random().toString(36).slice(2, 9);

export const useOptimizeStore = create<OptimizeStore>((set, get) => ({
  status: 'idle',
  progress: 0,
  error: null,
  bestParams: null,
  bestScore: null,
  grid: null,
  trials: [],
  strategyId: 'ma_cross',
  symbol: 'BTC/USDT',
  timeframe: '1h',
  source: 'test',
  paramSpace: [
    { id: uid(), name: 'fast_period', min: 5, max: 20, step: 1 },
    { id: uid(), name: 'slow_period', min: 21, max: 60, step: 1 },
  ],
  setStrategy: (id) => set({ strategyId: id }),
  setMarket: (m) => set(m),
  addParam: (name) =>
    set((s) => ({ paramSpace: [...s.paramSpace, { id: uid(), name, min: 1, max: 10, step: 1 }] })),
  updateParam: (id, patch) =>
    set((s) => ({ paramSpace: s.paramSpace.map((p) => (p.id === id ? { ...p, ...patch } : p)) })),
  removeParam: (id) =>
    set((s) => ({ paramSpace: s.paramSpace.filter((p) => p.id !== id) })),
  runOptimization: async () => {
    const { strategyId, symbol, timeframe, source, paramSpace } = get();
    set({ status: 'running', progress: 0, error: null, bestParams: null, bestScore: null, grid: null, trials: [] });
    try {
      const { task_id } = await api.runOptimize({
        strategy_id: strategyId,
        symbol,
        timeframe,
        source,
        param_space: paramSpace.map((p) => ({ name: p.name, min: p.min, max: p.max, step: p.step })),
      });
      const poll = setInterval(async () => {
        try {
          const data = await api.getOptimizeResults(task_id);
          set({ progress: data.status === 'completed' ? 100 : 50 });
          if (data.status === 'completed') {
            clearInterval(poll);
            set({ status: 'completed', bestParams: data.best_params, bestScore: data.best_score, grid: data.grid, trials: data.trials });
          } else if (data.status === 'error') {
            clearInterval(poll);
            set({ status: 'error', error: (data as any).error ?? 'optimization failed' });
          }
        } catch (e) {
          clearInterval(poll);
          set({ status: 'error', error: 'polling failed' });
        }
      }, 1500);
    } catch (e: any) {
      set({ status: 'error', error: e?.message ?? 'failed to start' });
    }
  },
  reset: () => set({ status: 'idle', progress: 0, error: null, bestParams: null, bestScore: null, grid: null, trials: [] }),
}));
```

- [ ] **Step 2: Commit**
```bash
git add frontend/src/stores/useOptimizeStore.ts
git commit -m "refactor(optimize): store uses unified api client + multi-param state"

---

### Task 6: Heatmap 组件（SVG）

**Files:**
- Create: `frontend/src/components/charts/Heatmap.tsx`

**Interfaces:**
- Consumes: `OptimizeGrid` 类型（Task 3），props: `{ grid: OptimizeGrid }`
- Produces: 渲染 2D 色阶矩阵，hover 显示数值

- [ ] **Step 1: 创建 Heatmap.tsx**
```tsx
'use client';

import React, { useState } from 'react';
import type { OptimizeGrid } from '@/types/api';

interface HeatmapProps {
  grid: OptimizeGrid;
}

export const Heatmap: React.FC<HeatmapProps> = ({ grid }) => {
  const [hover, setHover] = useState<{ x: number; y: number; v: number | null } | null>(null);
  const { param_x, param_y, x_values, y_values, scores } = grid;

  const flat = scores.flat().filter((v): v is number => v !== null);
  const min = flat.length ? Math.min(...flat) : 0;
  const max = flat.length ? Math.max(...flat) : 1;
  const span = max - min || 1;

  const colorFor = (v: number | null) => {
    if (v === null) return 'rgba(255,255,255,0.04)';
    const t = (v - min) / span;
    // danger (red) -> neutral -> success (green)
    if (t < 0.5) {
      const k = t / 0.5;
      return `rgba(${Math.round(220 + k * 35)}, ${Math.round(70 + k * 120)}, ${Math.round(70 + k * 60)}, 0.85)`;
    }
    const k = (t - 0.5) / 0.5;
    return `rgba(${Math.round(80 - k * 40)}, ${Math.round(200 + k * 30)}, ${Math.round(120 - k * 40)}, 0.85)`;
  };

  const cell = 38;
  const labelW = 56;
  const labelH = 28;
  const w = labelW + x_values.length * cell;
  const h = labelH + y_values.length * cell;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs font-mono text-textSecondary">
        <span>{param_x} (x) × {param_y} (y)</span>
        <span>{min.toFixed(2)} → {max.toFixed(2)}</span>
      </div>
      <svg width={w} height={h} className="max-w-full">
        {y_values.map((yv, yi) =>
          x_values.map((xv, xi) => {
            const v = scores[yi]?.[xi] ?? null;
            return (
              <rect
                key={`${xi}-${yi}`}
                x={labelW + xi * cell}
                y={labelH + yi * cell}
                width={cell - 2}
                height={cell - 2}
                rx={3}
                fill={colorFor(v)}
                onMouseEnter={() => setHover({ x: xi, y: yi, v })}
                onMouseLeave={() => setHover(null)}
                className="cursor-pointer transition-opacity hover:opacity-80"
              />
            );
          })
        )}
        {/* axis labels */}
        {x_values.map((xv, xi) => (
          <text key={`xl-${xi}`} x={labelW + xi * cell + cell / 2} y={labelH - 8} textAnchor="middle" className="fill-textSecondary" fontSize={10}>
            {xv}
          </text>
        ))}
        {y_values.map((yv, yi) => (
          <text key={`yl-${yi}`} x={labelW - 6} y={labelH + yi * cell + cell / 2 + 3} textAnchor="end" className="fill-textSecondary" fontSize={10}>
            {yv}
          </text>
        ))}
      </svg>
      {hover && (
        <div className="text-xs font-mono text-textSecondary">
          {param_x}={x_values[hover.x]}, {param_y}={y_values[hover.y]} →{' '}
          <span className={hover.v !== null && hover.v >= 0 ? 'text-success' : 'text-danger'}>
            {hover.v === null ? 'n/a' : hover.v.toFixed(3)}
          </span>
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 2: Commit**
```bash
git add frontend/src/components/charts/Heatmap.tsx
git commit -m "feat(optimize): add Heatmap SVG component"

---

### Task 7: ParamImportanceBar + ConvergenceChart 组件

**Files:**
- Create: `frontend/src/components/charts/ParamImportanceBar.tsx`
- Create: `frontend/src/components/charts/ConvergenceChart.tsx`

**Interfaces:**
- Consumes: `OptimizeResult.trials` (Task 3)
- Produces: ParamImportanceBar（每参数 score 分布条形图）、ConvergenceChart（best score over trials 收敛曲线）

- [ ] **Step 1: 创建 ParamImportanceBar.tsx**
```tsx
'use client';

import React from 'react';

interface Trial {
  params: Record<string, any>;
  score: number;
}

interface Props {
  trials: Trial[];
}

export const ParamImportanceBar: React.FC<Props> = ({ trials }) => {
  if (!trials.length) return null;
  const keys = Object.keys(trials[0].params);
  // 每参数：按取值聚合平均 score
  const agg: Record<string, { sum: number; n: number }> = {};
  for (const t of trials) {
    for (const k of keys) {
      agg[k] = agg[k] || { sum: 0, n: 0 };
      agg[k].sum += t.score;
      agg[k].n += 1;
    }
  }
  const rows = keys.map((k) => ({ k, avg: agg[k].n ? agg[k].sum / agg[k].n : 0 }));
  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
  return (
    <div className="space-y-3">
      {rows.map((r) => {
        const pct = (Math.abs(r.avg) / maxAbs) * 100;
        const pos = r.avg >= 0;
        return (
          <div key={r.k} className="space-y-1">
            <div className="flex justify-between text-xs font-mono text-textSecondary">
              <span>{r.k}</span>
              <span className={pos ? 'text-success' : 'text-danger'}>{r.avg.toFixed(3)}</span>
            </div>
            <div className="h-2 rounded-full bg-surface overflow-hidden">
              <div
                className={`h-full rounded-full ${pos ? 'bg-success' : 'bg-danger'}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
};
```

- [ ] **Step 2: 创建 ConvergenceChart.tsx（复用 lightweight-charts）**
```tsx
'use client';

import React, { useEffect, useRef } from 'react';
import { createChart, IChartApi, LineSeries, UTCTimestamp } from 'lightweight-charts';

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
    const series = chart.addSeries(LineSeries, { color: '#5b9dff', lineWidth: 2 });
    // best-so-far
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
```

- [ ] **Step 3: Commit**
```bash
git add frontend/src/components/charts/ParamImportanceBar.tsx frontend/src/components/charts/ConvergenceChart.tsx
git commit -m "feat(optimize): add ParamImportanceBar + ConvergenceChart"

---

### Task 8: optimize 页重构 + 部署验证

**Files:**
- Modify: `frontend/src/app/optimize/page.tsx` (整文件重写)
- Modify: `frontend/src/components/backtest/MetricsCard.tsx` (确认导出，供复用；若未导出则补 `export`)

**Interfaces:**
- Consumes: `useOptimizeStore` (Task 5), `Heatmap`/`ParamImportanceBar`/`ConvergenceChart` (Task 6/7), `useDataStore` (现有), `api.getTemplates`/`api.listUserStrategies` (现有)
- Produces: 完整 optimize 页 UI + 验证脚本

- [ ] **Step 1: 重写 optimize/page.tsx**
```tsx
'use client';

import React, { useEffect, useState } from 'react';
import { useDataStore } from '@/stores/useDataStore';
import { useOptimizeStore, ParamRangeUI } from '@/stores/useOptimizeStore';
import api from '@/lib/api';
import { StrategyTemplate, UserStrategy } from '@/types/api';
import { Card } from '@/components/ui/Card';
import { PageShell } from '@/components/layout/PageShell';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Input } from '@/components/ui/Input';
import { MetricsCard } from '@/components/backtest/MetricsCard';
import { Heatmap } from '@/components/charts/Heatmap';
import { ParamImportanceBar } from '@/components/charts/ParamImportanceBar';
import { ConvergenceChart } from '@/components/charts/ConvergenceChart';

export default function OptimizePage() {
  const { symbols, loadSymbols, setSymbol, setTimeframe, setSource } = useDataStore();
  const {
    status, progress, error, bestParams, bestScore, grid, trials,
    strategyId, paramSpace, symbol, timeframe, source,
    setStrategy, setMarket, addParam, updateParam, removeParam, runOptimization, reset,
  } = useOptimizeStore();

  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [userStrategies, setUserStrategies] = useState<UserStrategy[]>([]);
  const [newParamName, setNewParamName] = useState('');

  useEffect(() => { loadSymbols(); }, [loadSymbols]);
  useEffect(() => {
    api.getTemplates().then(setTemplates).catch(() => setTemplates([]));
    api.listUserStrategies().then(setUserStrategies).catch(() => setUserStrategies([]));
  }, []);

  const onSymbol = (v: string) => { setSymbol(v); setMarket({ symbol: v, timeframe, source }); };
  const onTf = (v: string) => { setTimeframe(v); setMarket({ symbol, timeframe: v, source }); };
  const onSrc = (v: string) => { setSource(v); setMarket({ symbol, timeframe, source: v }); };

  const builtinOptions = templates.filter((t) => !t.id.startsWith('user_')).map((t) => ({ label: t.name, value: t.id }));
  const userOptions = userStrategies.map((s) => ({ label: `我的：${s.name}`, value: `user_${s.id}` }));

  const handleAddParam = () => {
    if (!newParamName.trim()) return;
    addParam(newParamName.trim());
    setNewParamName('');
  };

  const handleApply = async () => {
    try { await api.applyBestParams(); reset(); }
    catch (e) { /* ignore */ }
  };

  return (
    <PageShell
      eyebrow="Optimize / search"
      title="參數優化"
      subtitle="多維網格搜索，自動收斂到最佳風險調整後參數組合，並以熱力圖視覺化參數空間。">
      {/* Config */}
      <Card>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Select label="Strategy" value={strategyId} onChange={(e) => setStrategy(e.target.value)}
            options={[...builtinOptions, ...userOptions]} />
          <Select label="Market" value={symbol} onChange={onSymbol}
            options={symbols.map((s) => ({ label: s.symbol, value: s.symbol }))} />
          <Select label="Timeframe" value={timeframe} onChange={onTf}
            options={[{label:'1h',value:'1h'},{label:'4h',value:'4h'},{label:'1d',value:'1d'}]} />
          <Select label="Data Source" value={source} onChange={onSrc}
            options={[{label:'Test',value:'test'},{label:'BingX',value:'bingx'}]} />
        </div>

        {/* param space editor */}
        <div className="mt-6 border-t border-border/10 pt-4 space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary">Parameter Space</h3>
          {paramSpace.map((p: ParamRangeUI) => (
            <div key={p.id} className="grid grid-cols-2 gap-3 sm:grid-cols-5 items-end">
              <Input label="Name" value={p.name} onChange={(e) => updateParam(p.id, { name: e.target.value })} />
              <Input label="Min" type="number" value={p.min} onChange={(e) => updateParam(p.id, { min: Number(e.target.value) })} />
              <Input label="Max" type="number" value={p.max} onChange={(e) => updateParam(p.id, { max: Number(e.target.value) })} />
              <Input label="Step" type="number" value={p.step} onChange={(e) => updateParam(p.id, { step: Number(e.target.value) })} />
              <Button variant="ghost" size="sm" onClick={() => removeParam(p.id)} disabled={paramSpace.length <= 1}>Remove</Button>
            </div>
          ))}
          <div className="flex gap-2">
            <Input label="New Param" value={newParamName} onChange={(e) => setNewParamName(e.target.value)} placeholder="e.g. rsi_period" />
            <Button variant="secondary" size="sm" onClick={handleAddParam}>Add</Button>
          </div>
        </div>

        <div className="mt-6 flex items-center justify-between border-t border-border/10 pt-4">
          <span className="text-sm font-mono text-textSecondary">
            {status === 'running' ? `Optimizing... ${Math.round(progress)}%` : status === 'error' ? `Error: ${error}` : 'Ready'}
          </span>
          <div className="flex gap-2">
            {status === 'completed' && (
              <Button variant="secondary" onClick={handleApply}>Apply Best Params</Button>
            )}
            <Button variant="primary" onClick={runOptimization} disabled={status === 'running'}>
              {status === 'running' ? 'Running...' : 'Run Grid Search'}
            </Button>
          </div>
        </div>
      </Card>

      {/* Results */}
      {status === 'completed' && bestParams && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <MetricsCard label="Best Sharpe" value={bestScore !== null ? bestScore.toFixed(3) : '—'} color={bestScore !== null && bestScore >= 0 ? 'positive' : 'negative'} />
            {Object.entries(bestParams).map(([k, v]) => (
              <MetricsCard key={k} label={k} value={String(v)} />
            ))}
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {grid && (
              <Card className="p-6">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary mb-4">Parameter Heatmap</h3>
                <Heatmap grid={grid} />
              </Card>
            )}
            <Card className="p-6">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary mb-4">Parameter Importance</h3>
              <ParamImportanceBar trials={trials} />
            </Card>
          </div>

          <Card className="p-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary mb-4">Convergence</h3>
            <ConvergenceChart trials={trials} />
          </Card>
        </div>
      )}
    </PageShell>
  );
}
```

- [ ] **Step 2: 确认 MetricsCard 导出**
检查 `frontend/src/components/backtest/MetricsCard.tsx` 第一行是否为 `export const MetricsCard` 或 `export function MetricsCard`。若否，改为导出。

- [ ] **Step 3: 类型检查 + build**
```bash
cd /root/Crypto-Backtesting-Lab/frontend
npm run build 2>&1 | tail -20
```
Expected: 编译成功，无 TS 错误。

- [ ] **Step 4: Commit 前端**
```bash
git add frontend/src/app/optimize/page.tsx frontend/src/components/backtest/MetricsCard.tsx
git commit -m "feat(optimize): rebuild page with multi-param + visualizations"
```

- [ ] **Step 5: 部署后端到 Railway**
```bash
cd /root/Crypto-Backtesting-Lab
git push origin master
export PATH="$HOME/.railway/bin:$PATH"
railway up --detach
```
等 ~3min 后验证：
```bash
B="https://affectionate-alignment-production-6d7e.up.railway.app"
curl -s -X POST "$B/optimize/run" -H "Content-Type: application/json" \
  -d '{"strategy_id":"ma_cross","symbol":"BTC/USDT","timeframe":"1h","source":"test","param_space":[{"name":"fast_period","min":5,"max":15,"step":5},{"name":"slow_period","min":20,"max":40,"step":10}]}' \
  -o /tmp/opt.json -w "HTTP %{http_code}\n"
TID=$(python3 -c "import json;print(json.load(open('/tmp/opt.json'))['task_id'])")
sleep 5
curl -s "$B/optimize/results/$TID" | python3 -c "import sys,json;d=json.load(sys.stdin);print('grid:',d.get('grid') is not None);print('best_score:',d.get('best_score'))"
```
Expected: `grid: True`, best_score 为数值。

- [ ] **Step 6: 部署前端到 Vercel + 验证**
```bash
cd /root/Crypto-Backtesting-Lab
VTOKEN=$(grep "^VERCEL_TOKEN=" /root/.env | cut -d= -f2- | tr -d '"')
export PATH="$HOME/.hermes/node/bin:$PATH"
npx vercel deploy --prod --token "$VTOKEN" --yes 2>&1 | tail -5
```
等部署完成后，浏览器打开 `https://quant-backtest-platform-v2.vercel.app/optimize`：选 2 参数 → Run Grid Search → 确认 Heatmap / Parameter Importance / Convergence 三图渲染，Best Sharpe 显示数值。
```
```
```
```
