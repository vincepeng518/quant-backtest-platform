'use client';

import React, { useEffect, useState } from 'react';
import { Card } from '@/components/ui/Card';
import { PageShell } from '@/components/layout/PageShell';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Input } from '@/components/ui/Input';
import { api } from '@/lib/api';
import { Spinner } from '@/components/ui/Spinner';
import type { StrategyTemplate, AnalysisResult } from '@/types/api';

export default function AnalysisPage() {
  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [strategyId, setStrategyId] = useState('ma_cross');
  const [method, setMethod] = useState('walk_forward');
  const [windows, setWindows] = useState(5);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getTemplates().then(setTemplates).catch(() => setTemplates([]));
  }, []);

  const handleAnalyze = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const tpl = templates.find((t) => t.id === strategyId);
      const param_space = (tpl?.params ?? []).map((p: any) => ({
        name: p.name,
        min: p.min ?? p.default ?? 5,
        max: p.max ?? p.default ?? 50,
        step: p.step ?? 1,
      }));
      const body =
        method === 'walk_forward'
          ? {
              strategy_id: strategyId,
              symbol: 'BTC/USDT',
              timeframe: '1h',
              param_space,
              n_windows: windows,
              algorithm: 'grid',
            }
          : {
              strategy_id: strategyId,
              symbol: 'BTC/USDT',
              timeframe: '1h',
              n_simulations: 500,
              initial_capital: 100000,
            };
      const { task_id } = await (method === 'walk_forward'
        ? api.runWalkForward(body)
        : api.runMonteCarlo(body));

      const poll = setInterval(async () => {
        const r = await api.getAnalysisResults(task_id);
        if (r.status === 'completed') {
          clearInterval(poll);
          setResult(r);
          setRunning(false);
        } else if (r.status === 'error') {
          clearInterval(poll);
          setError((r as any).error ?? 'analysis failed');
          setRunning(false);
        }
      }, 1000);
    } catch (e: any) {
      setError(e?.message ?? 'request failed');
      setRunning(false);
    }
  };

  const s = result?.summary ?? {};

  return (
    <PageShell
      eyebrow="Analysis / robustness"
      title="穩健性驗證"
      subtitle="Walk-Forward 樣本外驗證與蒙地卡羅模擬，量化策略在未知行情下的存活機率與破產風險。"
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Select
          label="Strategy"
          value={strategyId}
          onChange={(e) => setStrategyId(e.target.value)}
          options={templates.map((t) => ({ label: t.name, value: t.id }))}
        />
        <Select
          label="Validation Protocol"
          value={method}
          onChange={(e) => setMethod(e.target.value)}
          options={[
            { label: 'Walk Forward Validation', value: 'walk_forward' },
            { label: 'Monte Carlo Stress Test', value: 'monte_carlo' },
          ]}
        />
        <Input
          label="Windows / Iterations"
          type="number"
          value={windows}
          onChange={(e) => setWindows(Number(e.target.value))}
        />
      </div>

      <div className="flex justify-between items-center bg-surface p-4 border-t border-border/10 select-none">
        <div className="flex items-center gap-2 text-sm font-mono text-textSecondary">
          {running ? (<><Spinner size="sm" /><span>Simulating pathways...</span></>) : error ? <span className="text-danger">Error: {error}</span> : <span>Ready</span>}
        </div>
        <Button onClick={handleAnalyze} disabled={running} variant="primary">
          {running ? 'Analyzing...' : 'Run Robustness Simulation'}
        </Button>
      </div>

      {result && (
        <Card className="space-y-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-accent border-b border-border/10 pb-4">
            {method === 'walk_forward'
              ? 'Walk-Forward Validation Report'
              : 'Monte Carlo Stress Test Report'}
          </h2>

          {method === 'walk_forward' ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 font-mono text-sm">
              <Metric label="OOS Sharpe (avg)" value={s.avg_oos_sharpe} digits={2} />
              <Metric label="OOS Return (avg)" value={s.avg_oos_return} digits={2} suffix="%" />
              <Metric label="Consistency" value={s.consistency} digits={0} suffix="%" />
              <Metric label="Sharpe Std" value={s.sharpe_std} digits={3} />
              <Metric label="Return Std" value={s.return_std} digits={3} />
              <Metric label="Windows" value={(s.windows ?? []).length} digits={0} />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 font-mono text-sm">
              <Metric label="Bankruptcy Prob" value={s.bankruptcy_prob} digits={2} suffix="%" danger />
              <Metric label="Expected Return" value={s.expected_return} digits={0} />
              <Metric label="VaR 95" value={s.var_95} digits={0} danger />
              <Metric label="CVaR 95" value={s.cvar_95} digits={0} danger />
              <Metric label="P50 Final" value={s.percentiles?.['50']} digits={0} />
              <Metric label="P95 Final" value={s.percentiles?.['95']} digits={0} success />
            </div>
          )}
        </Card>
      )}
    </PageShell>
  );
}

function Metric({
  label,
  value,
  digits = 2,
  suffix = '',
  danger = false,
  success = false,
}: {
  label: string;
  value?: number;
  digits?: number;
  suffix?: string;
  danger?: boolean;
  success?: boolean;
}) {
  const color = danger ? 'text-danger' : success ? 'text-success' : 'text-text';
  return (
    <div>
      <span className="text-textSecondary block text-xs uppercase mb-1">{label}</span>
      <span className={`text-xl font-bold ${color}`}>
        {value === undefined || value === null ? '—' : value.toFixed(digits)}
        {suffix}
      </span>
    </div>
  );
}
