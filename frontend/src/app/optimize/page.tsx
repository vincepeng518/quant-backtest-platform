'use client';

import React, { Suspense, useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useOptimizeStore } from '@/stores/useOptimizeStore';
import { Card } from '@/components/ui/Card';
import { PageShell } from '@/components/layout/PageShell';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { MetricsCard } from '@/components/ui/MetricsCard';
import { Heatmap } from '@/components/charts/Heatmap';
import { ParamImportanceBar } from '@/components/charts/ParamImportanceBar';
import { ConvergenceChart } from '@/components/charts/ConvergenceChart';
import api from '@/lib/api';
import { RealismPanel } from '@/components/realism/RealismPanel';

const FALLBACK_STRATEGIES = [
  { label: 'Moving Average Cross', value: 'ma_cross' },
  { label: 'RSI Reversion', value: 'rsi_reversion' },
  { label: 'Breakout', value: 'breakout' },
  { label: 'Pairs Trade', value: 'pairs' },
  { label: 'Stat Arb', value: 'stat_arb' },
];

const SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT'];
const TIMEFRAMES = ['15m', '30m', '45m', '1h', '4h', '1d'];
const SOURCES = [
  { label: 'Test (offline)', value: 'test' },
  { label: 'BingX', value: 'bingx' },
];

export default function OptimizePage() {
  return (
    <Suspense fallback={null}>
      <OptimizeView />
    </Suspense>
  );
}

function OptimizeView() {
  const {
    status, progress, error, bestParams, bestScore, grid, trials,
    strategyId, symbol, timeframe, source, paramSpace,
    enableFunding, fundingInterval, fundingRate,
    enablePerp, leverage, maintMargin,
    enableExchange, makerFee, takerFee, latencyBars, bookSlippage,
    makerProbability, forceLimit,
    algorithm, maxTrials,
    setStrategy, setMarket, addParam, updateParam, removeParam, runOptimization, reset,
  } = useOptimizeStore();

  const router = useRouter();

  const searchParams = useSearchParams();
  const [strategyOptions, setStrategyOptions] = useState<{ label: string; value: string }[]>(FALLBACK_STRATEGIES);
  const [templates, setTemplates] = useState<any[]>([]);
  const [userStrategies, setUserStrategies] = useState<any[]>([]);

  // P8: dynamically list builtin templates + user-uploaded strategies
  useEffect(() => {
    Promise.allSettled([api.getTemplates(), api.listUserStrategies()])
      .then(([t, u]) => {
        const builtin = t.status === 'fulfilled'
          ? (t.value as any[]).map((x) => ({ label: x.name, value: x.id }))
          : [];
        const user = u.status === 'fulfilled'
          ? (u.value as any[]).map((s) => ({ label: `我的：${s.name}`, value: `user_${s.id}` }))
          : [];
        const merged = [...user, ...builtin.filter((b) => !user.some((x) => x.value === b.value))];
        // 如果 API 都失敗, 用 fallback (但優先真實數據)
        setStrategyOptions(merged.length ? merged : FALLBACK_STRATEGIES);
        if (t.status === 'fulfilled') setTemplates(t.value as any[]);
        if (u.status === 'fulfilled') setUserStrategies(u.value as any[]);
      });
  }, []);

  // Resolve a strategy's template params (for param-space rebuild on switch).
  const paramsFor = (id: string): { name: string; type?: string; min?: number; max?: number; step?: number }[] => {
    const tpl = templates.find((t) => t.id === id);
    if (tpl && Array.isArray(tpl.params)) return tpl.params;
    const us = userStrategies.find((s) => `user_${s.id}` === id);
    if (us && Array.isArray((us as any).params)) return (us as any).params;
    return [];
  };

  // P8: preselect from ?strategy= (e.g. user_xxxx) coming from /strategies
  useEffect(() => {
    const pref = searchParams.get('strategy');
    if (pref && strategyOptions.some((o) => o.value === pref)) {
      setStrategy(pref, paramsFor(pref));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategyOptions]);

  return (
    <PageShell
      eyebrow="Optimize / search"
      title="參數優化"
      subtitle="網格搜索並行掃參，自動收斂到最佳風險調整後的參數組合與夏普比率峰值。"
    >
      {/* Config: strategy + market */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <Select label="Strategy" value={strategyId} onChange={(e) => setStrategy(e.target.value, paramsFor(e.target.value))} options={strategyOptions} />
        <Select label="Symbol" value={symbol} onChange={(e) => setMarket({ symbol: e.target.value, timeframe, source })} options={SYMBOLS.map((s) => ({ label: s, value: s }))} />
        <Select label="Timeframe" value={timeframe} onChange={(e) => setMarket({ symbol, timeframe: e.target.value, source })} options={TIMEFRAMES.map((t) => ({ label: t, value: t }))} />
        <Select label="Data Source" value={source} onChange={(e) => setMarket({ symbol, timeframe, source: e.target.value })} options={SOURCES} />
        <Select
          label="Algorithm"
          value={algorithm}
          onChange={(e) => useOptimizeStore.setState({ algorithm: e.target.value as any })}
          options={[
            { label: 'Grid Search (brute)', value: 'grid' },
            { label: 'Bayesian (smart)', value: 'bayesian' },
            { label: 'Genetic (evolve)', value: 'genetic' },
          ]}
        />
        <Input
          label="Max Trials"
          type="number"
          value={maxTrials}
          onChange={(e) => useOptimizeStore.setState({ maxTrials: Number(e.target.value) })}
        />
      </div>

      {/* Param space editor */}
      <Card className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-accent">Parameter Space</h2>
          <Button variant="ghost" onClick={() => addParam(`param_${paramSpace.length + 1}`)}>+ Add Parameter</Button>
        </div>
        <div className="space-y-3">
          {paramSpace.map((p) => (
            <div key={p.id} className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
              <Input label="Name" value={p.name} onChange={(e) => updateParam(p.id, { name: e.target.value })} />
              <Input label="Min" type="number" value={p.min} onChange={(e) => updateParam(p.id, { min: Number(e.target.value) })} />
              <Input label="Max" type="number" value={p.max} onChange={(e) => updateParam(p.id, { max: Number(e.target.value) })} />
              <Input label="Step" type="number" value={p.step} onChange={(e) => updateParam(p.id, { step: Number(e.target.value) })} />
              <Button variant="ghost" onClick={() => removeParam(p.id)} disabled={paramSpace.length <= 1}>Remove</Button>
            </div>
          ))}
        </div>
      </Card>

      {/* Engine realism (opt-in) */}
      <Card className="space-y-4">
        <RealismPanel
          state={{
            enableFunding, fundingInterval, fundingRate,
            enablePerp, leverage, maintMargin,
            enableExchange, makerFee, takerFee, latencyBars, bookSlippage,
            makerProbability, forceLimit,
          }}
          handlers={{
            setEnableFunding: (v) => useOptimizeStore.setState({ enableFunding: v }),
            setFundingInterval: (v) => useOptimizeStore.setState({ fundingInterval: v }),
            setFundingRate: (v) => useOptimizeStore.setState({ fundingRate: v }),
            setEnablePerp: (v) => useOptimizeStore.setState({ enablePerp: v }),
            setLeverage: (v) => useOptimizeStore.setState({ leverage: v }),
            setMaintMargin: (v) => useOptimizeStore.setState({ maintMargin: v }),
            setEnableExchange: (v) => useOptimizeStore.setState({ enableExchange: v }),
            setMakerFee: (v) => useOptimizeStore.setState({ makerFee: v }),
            setTakerFee: (v) => useOptimizeStore.setState({ takerFee: v }),
            setLatencyBars: (v) => useOptimizeStore.setState({ latencyBars: v }),
            setBookSlippage: (v) => useOptimizeStore.setState({ bookSlippage: v }),
            setMakerProbability: (v) => useOptimizeStore.setState({ makerProbability: v }),
            setForceLimit: (v) => useOptimizeStore.setState({ forceLimit: v }),
          }}
        />
      </Card>

      {/* Run bar */}
      <div className="flex justify-between items-center bg-surface p-4 border-t border-border/10 select-none">
        <div className="text-sm font-mono text-textSecondary">
          {status === 'running' ? `Optimizing… ${Math.round(progress)}%` : status === 'error' ? `Error: ${error}` : 'Ready'}
        </div>
        <div className="flex gap-3">
          {status === 'completed' && (
            <Button variant="ghost" onClick={reset}>Reset</Button>
          )}
          <Button onClick={runOptimization} disabled={status === 'running'} variant="primary">
            {status === 'running' ? 'Optimizing…' : 'Start Optimization'}
          </Button>
        </div>
      </div>

      {/* Results */}
      {status === 'completed' && bestParams && (
        <div className="space-y-6">
          <MetricsCard
            items={[
              { label: 'Best Sharpe', value: bestScore !== null ? bestScore.toFixed(3) : '—', accent: 'success' },
              ...Object.entries(bestParams).map(([k, v]) => ({ label: k, value: String(v) })),
            ]}
          />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="space-y-4">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-accent">Parameter Heatmap</h3>
              {grid ? <Heatmap grid={grid} /> : <p className="text-sm text-textSecondary">Heatmap available for exactly 2 range parameters.</p>}
            </Card>
            <Card className="space-y-4">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-accent">Parameter Importance</h3>
              <ParamImportanceBar trials={trials} />
            </Card>
          </div>

          <Card className="space-y-4">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-accent">Convergence (best score over trials)</h3>
            <ConvergenceChart trials={trials} />
          </Card>

          <div className="flex justify-end">
            <Button
              variant="primary"
              onClick={() => router.push(`/backtest?strategy=${encodeURIComponent(strategyId)}&params=${encodeURIComponent(JSON.stringify(bestParams))}`)}
            >
              Apply Best Params to Backtest
            </Button>
          </div>
        </div>
      )}
    </PageShell>
  );
}
