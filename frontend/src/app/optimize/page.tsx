'use client';

import React, { useState } from 'react';
import { useOptimizeStore } from '@/stores/useOptimizeStore';
import { Card } from '@/components/ui/Card';
import { PageShell } from '@/components/layout/PageShell';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';

export default function OptimizePage() {
  const {
    status,
    progress,
    bestParams,
    bestScore,
    paramSpace,
    setStrategy,
    updateParam,
    runOptimization,
  } = useOptimizeStore();

  const [strategy, setStrategyLocal] = useState('ma_cross');
  const [paramName, setParamName] = useState('fast_period');
  const [minVal, setMinVal] = useState(10);
  const [maxVal, setMaxVal] = useState(50);
  const [stepVal, setStepVal] = useState(2);

  const handleOptimize = () => {
    setStrategy(strategy);
    const target = paramSpace.find((p) => p.name === paramName);
    if (target) {
      updateParam(target.id, { min: Number(minVal), max: Number(maxVal), step: Number(stepVal) });
    }
    runOptimization();
  };

  return (
    <PageShell
      eyebrow="Optimize / search"
      title="參數優化"
      subtitle="網格搜索並行掃參，自動收斂到最佳風險調整後的參數組合與夏普比率峰值。"
    >
      {/* Parameters configuration */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
        <Select
          label="Strategy Model"
          value={strategy}
          onChange={(e) => setStrategy(e.target.value)}
          options={[{ label: 'Moving Average Cross', value: 'ma_cross' }]}
        />
        <Select
          label="Target Parameter"
          value={paramName}
          onChange={(e) => setParamName(e.target.value)}
          options={[
            { label: 'Fast Period', value: 'fast_period' },
            { label: 'Slow Period', value: 'slow_period' },
          ]}
        />
        <Input
          label="Min Safe Bound"
          type="number"
          value={minVal}
          onChange={(e) => setMinVal(Number(e.target.value))}
        />
        <Input
          label="Max Safe Bound"
          type="number"
          value={maxVal}
          onChange={(e) => setMaxVal(Number(e.target.value))}
        />
        <Input
          label="Step Granularity"
          type="number"
          value={stepVal}
          onChange={(e) => setStepVal(Number(e.target.value))}
        />
      </div>

      <div className="flex justify-between items-center bg-surface p-4 border-t border-border/10 select-none">
        <div className="text-sm font-mono text-textSecondary">
          {status === 'running' ? `Optimization Progress: ${Math.round(progress)}%` : 'Ready'}
        </div>
        <Button onClick={handleOptimize} disabled={status === 'running'} variant="primary">
          {status === 'running' ? 'Optimizing...' : 'Start Search Space Iteration'}
        </Button>
      </div>

      {status === 'completed' && bestParams && (
        <Card className="space-y-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-accent border-b border-border/10 pb-4">
            Optimal Parameters Found
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 font-mono text-sm">
            <div>
              <span className="text-textSecondary block text-xs uppercase mb-1">Score (Sharpe Ratio)</span>
              <span className="text-xl font-bold text-success">{bestScore?.toFixed(3)}</span>
            </div>
            {Object.entries(bestParams).map(([key, val]) => (
              <div key={key}>
                <span className="text-textSecondary block text-xs uppercase mb-1">{key}</span>
                <span className="text-lg font-semibold text-text">{String(val)}</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </PageShell>
  );
};
