'use client';

import React, { useState } from 'react';
import { PageShell } from '@/components/layout/PageShell';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { api } from '@/lib/api';
import { useToastStore } from '@/stores/useToastStore';

interface PFResult {
  status: string;
  error?: string;
  warnings?: string[];
  symbols?: string[];
  correlation_matrix?: Record<string, Record<string, number>>;
  portfolio_metrics?: any;
  hedge_report?: any;
  pf_individual_metrics?: Record<string, any>;
  portfolio_equity?: number[];
  weights?: Record<string, number>;
}

export default function PortfolioPage() {
  const [symbols, setSymbols] = useState<string[]>(['BTC/USDT', 'ETH/USDT', 'SOL/USDT']);
  const [timeframe, setTimeframe] = useState('1d');
  const [startDate, setStartDate] = useState('2025-01-01');
  const [endDate, setEndDate] = useState('2025-06-01');
  const [templateId, setTemplateId] = useState('ma_cross');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<PFResult | null>(null);
  const [daysBack, setDaysBack] = useState(20);
  const push = useToastStore((s) => s.push);

  const CANDS = ['BTC/USDT','ETH/USDT','SOL/USDT','BNB/USDT','XRP/USDT','ADA/USDT','AVAX/USDT','LINK/USDT','DOGE/USDT','LTC/USDT'];

  const toggleSym = (s: string) => {
    setSymbols((prev) => prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]);
  };

  const run = async () => {
    if (symbols.length < 2) { push({ kind: 'danger', title: '需選至少 2 個標的' }); return; }
    setRunning(true);
    setResult(null);
    try {
      const r: PFResult = await api.runPortfolio({
        symbols,
        strategy: { template_id: templateId, params: {} },
        timeframe,
        start_date: startDate,
        end_date: endDate,
        initial_capital: 100000,
        commission: 0.0004,
        source: 'bingx',
      });
      setResult(r);
      if (r.status !== 'ok') push({ kind: 'danger', title: '組合回測失敗', message: r.error });
      else if (r.warnings?.length) push({ kind: 'danger', title: '⚠ 組合警告', message: r.warnings.join(' | ') });
    } catch (e: any) {
      push({ kind: 'danger', title: '執行失敗', message: String(e?.message ?? e) });
    } finally {
      setRunning(false);
    }
  };

  const maxPnl = (equity: number[] | undefined) => equity && equity.length ? Math.max(...equity.map(Math.abs)) : 1;
  const fmt = (n: number | null | undefined, d = 2) => n == null || Number.isNaN(n) ? '—' : Number(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

  return (
    <PageShell eyebrow="Portfolio / hedge" title="多標的組合對沖回測" subtitle="多標的各跑策略 → 日回報空間加權組合 → 相關性矩陣驗證對沖價值。">
      {/* 設定 */}
      <Card className="p-5 space-y-4">
        <div>
          <p className="text-xs font-mono text-textSecondary mb-2">選擇標的（≥2）</p>
          <div className="flex flex-wrap gap-2">
            {CANDS.map((s) => (
              <button
                key={s}
                onClick={() => toggleSym(s)}
                className={`px-3 py-1.5 rounded-md text-xs font-mono transition-colors ${
                  symbols.includes(s) ? 'bg-accent text-background font-medium' : 'bg-surface text-textSecondary hover:text-text'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
          <p className="text-[11px] text-textSecondary font-mono mt-1.5">已選：{symbols.join(', ') || '（無）'}</p>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <label className="text-xs font-mono text-textSecondary space-y-1">
            策略模板
            <select value={templateId} onChange={(e) => setTemplateId(e.target.value)}
              className="w-full bg-background border border-border/10 rounded-md px-2 py-1.5 text-sm text-text">
              <option value="ma_cross">ma_cross</option>
              <option value="breakout">breakout</option>
            </select>
          </label>
          <label className="text-xs font-mono text-textSecondary space-y-1">
            Timeframe
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}
              className="w-full bg-background border border-border/10 rounded-md px-2 py-1.5 text-sm text-text">
              {['1d','4h','1h'].map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label className="text-xs font-mono text-textSecondary space-y-1">
            Start
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
              className="w-full bg-background border border-border/10 rounded-md px-2 py-1.5 text-sm text-text" />
          </label>
          <label className="text-xs font-mono text-textSecondary space-y-1">
            End
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
              className="w-full bg-background border border-border/10 rounded-md px-2 py-1.5 text-sm text-text" />
          </label>
          <div className="flex items-end">
            <Button onClick={run} disabled={running} className="w-full">
              {running ? '組合回測中…' : '跑組合回測'}
            </Button>
          </div>
        </div>
      </Card>

      {running && (
        <Card className="p-8 flex justify-center"><Spinner size="lg" /></Card>
      )}

      {result && result.status === 'ok' && (
        <>
          {/* 相關性矩陣 */}
          <Card className="p-5">
            <h3 className="text-sm font-semibold text-text mb-3">相關性矩陣（標的日回報 Pearson 相關係數）</h3>
            {result.correlation_matrix && (
              <div className="overflow-x-auto">
                <table className="text-xs font-mono">
                  <thead>
                    <tr className="text-textSecondary">
                      <th className="px-2 py-1" />
                      {(result.symbols || []).map((s) => (
                        <th key={s} className="px-3 py-1 text-right">{s.split('/')[0]}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(result.symbols || []).map((a) => (
                      <tr key={a}>
                        <td className="px-2 py-1 text-textSecondary font-semibold">{a.split('/')[0]}</td>
                        {(result.symbols || []).map((b) => {
                          const c = result.correlation_matrix?.[a]?.[b] ?? 0;
                          const bg = c > 0.3 ? 'bg-success/20 text-success' : c < -0.2 ? 'bg-danger/20 text-danger' : 'bg-surface text-text';
                          return (
                            <td key={b} className={`px-3 py-1 text-right rounded ${bg}`}>{fmt(c, 3)}</td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {result.warnings?.length ? (
              <p className="text-[11px] text-danger font-mono mt-2">⚠ {result.warnings.join('；')}</p>
            ) : null}
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* 組合風險 */}
            <Card className="p-5">
              <h3 className="text-sm font-semibold text-text mb-3">組合風險（日回報空間加權）</h3>
              <div className="space-y-2 text-sm font-mono">
                <Row label="Sharpe" v={fmt(result.portfolio_metrics?.sharpe, 3)} />
                <Row label="年化波動" v={fmt(result.portfolio_metrics?.volatility_annual, 4)} />
                <Row label="總報酬" v={`${fmt(result.portfolio_metrics?.total_return, 4)}`} />
                <Row label="最大回撤" v={`${fmt(result.portfolio_metrics?.max_drawdown, 4)}`} />
                <Row label="樣本天數" v={String(result.portfolio_metrics?.n)} />
              </div>
            </Card>
            {/* 對沖報告 */}
            <Card className="p-5">
              <h3 className="text-sm font-semibold text-text mb-3">對沖價值報告</h3>
              <div className="space-y-2 text-sm font-mono">
                <Row label="最佳單標波動" v={fmt(result.hedge_report?.best_single_volatility, 4)} />
                <Row label="組合波動" v={fmt(result.hedge_report?.portfolio_volatility, 4)} />
                <Row label="組合相對最佳單標降幅" v={`${fmt(result.hedge_report?.portfolio_vol_reduction, 4)}`} />
                <Row label="平均對 corr" v={fmt(result.hedge_report?.avg_pair_corr, 3)} />
                <div className="pt-1 text-[11px] text-textSecondary">
                  {result.hedge_report?.negative_corr_pairs?.length
                    ? `負相關對：${result.hedge_report.negative_corr_pairs.map((p: any) => `${p.a.split('/')[0]}-${p.b.split('/')[0]}:${p.corr}`).join(', ')}`
                    : '無負相關標的對（此組合無框內對沖腿）'}
                </div>
              </div>
            </Card>
          </div>

          {/* 個別風險 */}
          <Card className="p-5">
            <h3 className="text-sm font-semibold text-text mb-3">各標的風險</h3>
            <div className="overflow-x-auto">
              <table className="text-xs font-mono w-full">
                <thead>
                  <tr className="text-textSecondary border-b border-border/10">
                    <th className="text-left py-1 pr-3">標的</th>
                    <th className="text-right py-1 pr-3">Sharpe</th>
                    <th className="text-right py-1 pr-3">年化波動</th>
                    <th className="text-right py-1 pr-3">總報酬</th>
                    <th className="text-right py-1 pr-3">最大回撤</th>
                  </tr>
                </thead>
                <tbody>
                  {(result.symbols || []).map((s) => {
                    const m = result.pf_individual_metrics?.[s] || {};
                    return (
                      <tr key={s} className="border-b border-border/5">
                        <td className="py-1.5 pr-3 font-medium text-text">{s}</td>
                        <td className="py-1.5 pr-3 text-right text-text">{fmt(m.sharpe, 3)}</td>
                        <td className="py-1.5 pr-3 text-right text-text">{fmt(m.volatility_annual, 4)}</td>
                        <td className="py-1.5 pr-3 text-right text-text">{fmt(m.total_return, 4)}</td>
                        <td className="py-1.5 pr-3 text-right text-text">{fmt(m.max_drawdown, 4)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          {/* 組合 equity 走勢 */}
          <Card className="p-5">
            <h3 className="text-sm font-semibold text-text mb-3">組合 Equity（起值 100）</h3>
            {daysBack > 0 && (
              <div className="flex items-center gap-2 mb-2 text-xs font-mono text-textSecondary">
                顯示最近
                <select value={daysBack} onChange={(e) => setDaysBack(Number(e.target.value))} className="bg-background border border-border/10 rounded px-1 py-0.5">
                  {[20, 50, 100, 500].map((n) => <option key={n} value={n}>{n} 點</option>)}
                </select>
              </div>
            )}
            <Sparkline equity={(result.portfolio_equity || []).slice(-daysBack)} maxA={maxPnl((result.portfolio_equity || []).slice(-daysBack))} />
          </Card>
        </>
      )}

      {result && result.status !== 'ok' && (
        <Card className="p-6">
          <p className="text-sm font-mono text-danger">組合回測失敗</p>
          <p className="text-xs font-mono text-textSecondary mt-2">{result.error}</p>
        </Card>
      )}
    </PageShell>
  );
}

function Row({ label, v }: { label: string; v: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-textSecondary">{label}</span>
      <span className="text-text">{v}</span>
    </div>
  );
}

function Sparkline({ equity, maxA }: { equity: number[]; maxA: number }) {
  if (!equity.length) return <p className="text-xs text-textSecondary">無資料</p>;
  const H = 160, W = 600, step = W / Math.max(1, equity.length - 1);
  const norm = (v: number) => maxA ? Math.max(0, H - (v / maxA) * H) : H / 2;
  const pts = equity.map((v, i) => `${(i * step).toFixed(1)},${norm(v).toFixed(1)}`);
  const color = equity[equity.length - 1] >= equity[0] ? '#36D399' : '#F87171';
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-40" preserveAspectRatio="none" width="100%">
      <polyline points={pts.join(' ')} fill="none" stroke={color} strokeWidth="1.5" />
      <line x1="0" y1={norm(equity[0])} x2={W} y2={norm(equity[0])} stroke="rgba(120,120,120,0.3)" strokeDasharray="4 4" />
    </svg>
  );
}
