'use client';

import React, { useState } from 'react';
import api from '@/lib/api';
import { Card } from '@/components/ui/Card';
import { PageShell } from '@/components/layout/PageShell';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Input } from '@/components/ui/Input';
import { MetricsCard } from '@/components/backtest/MetricsCard';
import { EmptyState } from '@/components/ui/EmptyState';
import { EquityCurve } from '@/components/charts/EquityCurve';

const VENUES = [
  { label: 'BingX', value: 'bingx' },
  { label: 'Binance', value: 'binance' },
  { label: 'Test (local)', value: 'test' },
];

function ArbView() {
  const [longVenue, setLongVenue] = useState('bingx');
  const [shortVenue, setShortVenue] = useState('binance');
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [entryThreshold, setEntryThreshold] = useState(0.003);
  const [exitThreshold, setExitThreshold] = useState(0.001);
  const [leverage, setLeverage] = useState(1);
  const [fundingEnabled, setFundingEnabled] = useState(false);
  const [useExchangeFees, setUseExchangeFees] = useState(true);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any | null>(null);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = {
        long_symbol: symbol,
        long_source: longVenue,
        short_symbol: symbol,
        short_source: shortVenue,
        timeframe,
        initial_capital: 100000,
        allocation_pct: 0.5,
        leverage,
        entry_threshold: Number(entryThreshold),
        exit_threshold: Number(exitThreshold),
        funding_enabled: fundingEnabled,
        long_exchange: { enabled: useExchangeFees },
        short_exchange: { enabled: useExchangeFees },
      };
      const res = await api.runArbitrage(payload);
      setResult(res);
    } catch (e: any) {
      setError(e?.message || 'Arbitrage run failed');
    } finally {
      setLoading(false);
    }
  };

  const equityData = (result?.equity_curve || []).map((v: number, i: number) => ({
    time: i,
    equity: v,
  }));

  return (
    <PageShell
      eyebrow="Arbitrage / venue"
      title="跨所套利"
      subtitle="雙邊持倉捕捉同一資產在不同交易所的價差與資金費率差。合約級手續費（maker/taker）與 funding 實景建模。"
    >
      <Card>
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-textSecondary">配置</h2>
          <span className="font-mono text-xs text-textSecondary">Basis Arbitrage</span>
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Select label="Long Venue" value={longVenue} onChange={(e) => setLongVenue(e.target.value)} options={VENUES} />
          <Select label="Short Venue" value={shortVenue} onChange={(e) => setShortVenue(e.target.value)} options={VENUES} />
          <Input label="Symbol" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
          <Select
            label="Timeframe"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            options={[
              { label: '1h', value: '1h' },
              { label: '4h', value: '4h' },
              { label: '1d', value: '1d' },
            ]}
          />
          <Input label="Entry Threshold" type="number" step={0.0005} value={entryThreshold} onChange={(e) => setEntryThreshold(Number(e.target.value))} />
          <Input label="Exit Threshold" type="number" step={0.0005} value={exitThreshold} onChange={(e) => setExitThreshold(Number(e.target.value))} />
          <Input label="Leverage" type="number" value={leverage} onChange={(e) => setLeverage(Number(e.target.value))} />
          <div className="flex items-end gap-4 pb-2">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={fundingEnabled} onChange={(e) => setFundingEnabled(e.target.checked)} />
              Funding
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={useExchangeFees} onChange={(e) => setUseExchangeFees(e.target.checked)} />
              Venue Fees
            </label>
          </div>
        </div>

        <div className="mt-6 flex items-center justify-between border-t border-border/10 pt-4">
          <span className="text-sm font-mono text-textSecondary">{loading ? 'Running...' : 'Ready'}</span>
          <Button onClick={run} disabled={loading} variant="primary">Run Arbitrage</Button>
        </div>
        {error && <p className="mt-3 text-sm font-mono text-danger">{error}</p>}
      </Card>

      {result && result.status === 'completed' ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <MetricsCard label="Total Return" value={`${result.metrics.total_return_pct.toFixed(2)}%`} color={result.metrics.total_pnl >= 0 ? 'positive' : 'negative'} />
            <MetricsCard label="Sharpe" value={result.metrics.sharpe_ratio.toFixed(2)} />
            <MetricsCard label="Max DD" value={`${(result.metrics.max_drawdown * 100).toFixed(2)}%`} color="negative" />
            <MetricsCard label="Win Rate" value={`${(result.metrics.win_rate * 100).toFixed(1)}%`} />
            <MetricsCard label="Trades" value={String(result.metrics.total_trades)} />
          </div>

          {equityData.length > 1 && (
            <Card className="p-0 overflow-hidden">
              <div className="p-6 pb-0">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary">Equity Curve</h3>
              </div>
              <EquityCurve data={equityData} theme="dark" />
            </Card>
          )}

          {result.trades?.length > 0 && (
            <Card className="p-0 overflow-hidden">
              <div className="flex items-center justify-between p-6 pb-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary">Trade Blotter</h3>
                <span className="text-xs font-mono text-textSecondary">{result.trades.length} fills</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm font-mono">
                  <thead>
                    <tr className="text-left text-xs uppercase text-textSecondary border-t border-border/10">
                      <th className="px-6 py-3">#</th>
                      <th className="px-6 py-3">Entry Time</th>
                      <th className="px-6 py-3 text-right">Entry</th>
                      <th className="px-6 py-3 text-right">Exit</th>
                      <th className="px-6 py-3 text-right">PnL</th>
                      <th className="px-6 py-3 text-right">Funding</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.map((t: any, i: number) => (
                      <tr key={i} className="border-t border-border/10 hover:bg-white/[0.02] transition-colors">
                        <td className="px-6 py-3 text-textSecondary">{i + 1}</td>
                        <td className="px-6 py-3 text-textSecondary">{t.entry_time}</td>
                        <td className="px-6 py-3 text-right text-text">{Number(t.entry_price).toFixed(2)}</td>
                        <td className="px-6 py-3 text-right text-text">{t.exit_price != null ? Number(t.exit_price).toFixed(2) : '—'}</td>
                        <td className={`px-6 py-3 text-right font-semibold ${Number(t.pnl) >= 0 ? 'text-success' : 'text-danger'}`}>
                          {Number(t.pnl).toFixed(2)}
                        </td>
                        <td className="px-6 py-3 text-right text-textSecondary">{Number(t.funding_paid).toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      ) : result ? (
        <Card><EmptyState title="No trades generated" description="Basis spread stayed within thresholds for this window. Widen entry/exit or pick a more divergent venue pair." /></Card>
      ) : null}
    </PageShell>
  );
}

export default function ArbitragePage() {
  return <ArbView />;
}
