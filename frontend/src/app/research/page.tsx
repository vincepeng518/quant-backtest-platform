'use client';
import React, { useEffect, useState } from 'react';
import { PageShell } from '@/components/layout/PageShell';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Spinner } from '@/components/ui/Spinner';
import { useResearchStore } from '@/stores/useResearchStore';
import { api } from '@/lib/api';
import type { StrategyTemplate } from '@/types/api';

export default function ResearchPage() {
  const s = useResearchStore();
  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  useEffect(() => { api.getTemplates().then(setTemplates).catch(() => setTemplates([])); }, []);
  const r = s.result?.summary ?? {};
  return (
    <PageShell eyebrow="Research / explore" title="市場與策略研究"
      subtitle="回測前哨：裸 K 線統計探索（波動/Hurst/regime/相關性）與輕量策略信號剖析。">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Select label="Type" value={s.type}
          onChange={(e) => s.set({ type: e.target.value as any })}
          options={[{ label: 'Market Research', value: 'market' }, { label: 'Signal Research', value: 'signal' }]} />
        <Select label="Symbol" value={s.symbol}
          onChange={(e) => s.set({ symbol: e.target.value })}
          options={['BTC/USDT', 'ETH/USDT', 'AAPL', 'GC=F', 'NVDA'].map((v) => ({ label: v, value: v }))} />
        <Select label="Timeframe" value={s.timeframe}
          onChange={(e) => s.set({ timeframe: e.target.value })}
          options={['5m', '15m', '1h', '4h', '1d'].map((v) => ({ label: v, value: v }))} />
      </div>
      {s.type === 'signal' && (
        <Select label="Strategy" value={s.strategyId}
          onChange={(e) => s.set({ strategyId: e.target.value })}
          options={templates.map((t) => ({ label: t.name, value: t.id }))} />
      )}
      <div className="flex justify-between items-center bg-surface p-4 border-t border-border/10">
        <div className="flex items-center gap-2 text-sm font-mono text-textSecondary">
          {s.status === 'running' ? <><Spinner size="sm" /><span>Researching...</span></>
            : s.error ? <span className="text-danger">Error: {s.error}</span> : <span>Ready</span>}
        </div>
        <Button onClick={() => s.run()} disabled={s.status === 'running'} variant="primary">
          {s.status === 'running' ? 'Running...' : 'Run Research'}
        </Button>
      </div>
      {s.result && s.type === 'market' && (
        <Card className="space-y-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-accent border-b border-border/10 pb-4">Market Profile</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 font-mono text-sm">
            <M label="Hurst" v={r.hurst} d={3} />
            <M label="Correlation(BTC)" v={r.correlation} d={3} />
            <M label="Ann. Vol" v={r.returns_stats?.annualized_vol} d={3} suffix="%" />
            <M label="Skew" v={r.returns_stats?.skew} d={3} />
            <M label="Kurtosis" v={r.returns_stats?.kurtosis} d={3} />
            <M label="Autocorr lag1" v={r.autocorrelation?.lag_1} d={3} />
          </div>
        </Card>
      )}
      {s.result && s.type === 'signal' && (
        <Card className="space-y-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-accent border-b border-border/10 pb-4">Signal Profile</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 font-mono text-sm">
            <M label="Long/Short Ratio" v={r.long_short_ratio} d={3} />
            <M label="Entry Percentile" v={r.entry_timing?.mean_percentile} d={3} />
            <M label="Fwd Return(5)" v={r.signal_forward_return?.mean} d={4} suffix="%" />
          </div>
        </Card>
      )}
    </PageShell>
  );
}
function M({ label, v, d = 2, suffix = '' }: { label: string; v?: number; d?: number; suffix?: string }) {
  return (<div><span className="text-textSecondary block text-xs uppercase mb-1">{label}</span>
    <span className="text-xl font-bold">{v === undefined || v === null ? '—' : v.toFixed(d) + suffix}</span></div>);
}
