'use client';

import React, { useState } from 'react';
import { Card } from '@/components/ui/Card';
import { PageShell } from '@/components/layout/PageShell';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Input } from '@/components/ui/Input';

export default function AnalysisPage() {
  const [method, setMethod] = useState('walk_forward');
  const [running, setRunning] = useState(false);
  const [reports, setReports] = useState<any>(null);

  const handleAnalyze = () => {
    setRunning(true);
    setTimeout(() => {
      setRunning(false);
      setReports({
        robustness: 0.85,
        failProbability: 0.05,
        oosReturn: 18.23,
      });
    }, 1500);
  };

  return (
    <PageShell
      eyebrow="Analysis / robustness"
      title="穩健性驗證"
      subtitle="Walk-Forward 樣本外驗證與蒙地卡羅模擬，量化策略在未知行情下的存活機率與破產風險。"
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Select
          label="Validation Protocol"
          value={method}
          onChange={(e) => setMethod(e.target.value)}
          options={[
            { label: 'Walk Forward Validation', value: 'walk_forward' },
            { label: 'Monte Carlo Stress Test', value: 'monte_carlo' },
          ]}
        />
        <Input label="Iterations Window" type="number" defaultValue={250} />
        <Input label="Confidence Delta" type="number" defaultValue={0.95} />
      </div>

      <div className="flex justify-between items-center bg-surface p-4 border-t border-border/10 select-none">
        <div className="text-sm font-mono text-textSecondary">
          {running ? 'Simulating pathways...' : 'Ready'}
        </div>
        <Button onClick={handleAnalyze} disabled={running} variant="primary">
          {running ? 'Analyzing...' : 'Run Robustness Simulation'}
        </Button>
      </div>

      {reports && (
        <Card className="space-y-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-accent border-b border-border/10 pb-4">
            Robustness & Stress Validation Report
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 font-mono text-sm">
            <div>
              <span className="text-textSecondary block text-xs uppercase mb-1">Robustness Index</span>
              <span className="text-xl font-bold text-success">{(reports.robustness * 100).toFixed(0)}%</span>
            </div>
            <div>
              <span className="text-textSecondary block text-xs uppercase mb-1">Probability of Ruin</span>
              <span className="text-xl font-bold text-danger">{(reports.failProbability * 100).toFixed(0)}%</span>
            </div>
            <div>
              <span className="text-textSecondary block text-xs uppercase mb-1">OOS Return (Weighted Avg)</span>
              <span className="text-xl font-bold text-text">{reports.oosReturn.toFixed(2)}%</span>
            </div>
          </div>
        </Card>
      )}
    </PageShell>
  );
};
