'use client';

import React, { useEffect, useState } from 'react';
import { useDataStore } from '@/stores/useDataStore';
import { useBacktestStore } from '@/stores/useBacktestStore';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Input } from '@/components/ui/Input';
import { MetricsCard } from '@/components/backtest/MetricsCard';
import { PriceChart } from '@/components/charts/PriceChart';
import { EquityCurve } from '@/components/charts/EquityCurve';
import { DrawdownChart } from '@/components/charts/DrawdownChart';

export default function BacktestPage() {
  const { symbols, ohlcv, loadSymbols, loadOHLCV } = useDataStore();
  const { runBacktest, results, status, progress, error } = useBacktestStore();

  const [symbol, setSymbol] = useState('');
  const [timeframe, setTimeframe] = useState('1h');
  const [fastPeriod, setFastPeriod] = useState(20);
  const [slowPeriod, setSlowPeriod] = useState(50);

  useEffect(() => {
    loadSymbols();
  }, [loadSymbols]);

  useEffect(() => {
    if (symbols.length > 0) {
      const defaultSymbol = symbols[0].symbol;
      setSymbol(defaultSymbol);
      loadOHLCV(defaultSymbol, timeframe);
    }
  }, [symbols, timeframe, loadOHLCV]);

  const handleRun = () => {
    runBacktest({
      strategy: {
        template_id: 'ma_cross',
        params: { fast_period: Number(fastPeriod), slow_period: Number(slowPeriod) },
      },
      symbol,
      timeframe,
      from: Math.floor(Date.now() / 1000) - 365 * 24 * 60 * 60, // 1 year ago
      to: Math.floor(Date.now() / 1000),
      risk: {
        initial_capital: 10000.0,
        commission: 0.001,
        slippage: 0.0005,
        max_position_pct: 1.0,
      },
    });
  };

  return (
    <div className="space-y-8">
      {/* Configuration Header Panel */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <Select
          label="Market Instrument"
          value={symbol}
          onChange={(e) => {
            setSymbol(e.target.value);
            loadOHLCV(e.target.value, timeframe);
          }}
          options={symbols.map((s) => ({ label: s.symbol, value: s.symbol }))}
        />
        <Select
          label="Timeframe"
          value={timeframe}
          onChange={(e) => {
            setTimeframe(e.target.value);
            loadOHLCV(symbol, e.target.value);
          }}
          options={[
            { label: '1 Minute', value: '1m' },
            { label: '5 Minutes', value: '5m' },
            { label: '15 Minutes', value: '15m' },
            { label: '1 Hour', value: '1h' },
            { label: '4 Hours', value: '4h' },
            { label: '1 Day', value: '1d' },
          ]}
        />
        <Input
          label="Fast MA Period"
          type="number"
          value={fastPeriod}
          onChange={(e) => setFastPeriod(Number(e.target.value))}
        />
        <Input
          label="Slow MA Period"
          type="number"
          value={slowPeriod}
          onChange={(e) => setSlowPeriod(Number(e.target.value))}
        />
      </div>

      <div className="flex justify-between items-center bg-surface p-4 border-t border-border/10 select-none">
        <div className="text-sm font-mono text-textSecondary">
          {status === 'running' ? `Backtesting Progress: ${Math.round(progress)}%` : 'Ready'}
        </div>
        <Button onClick={handleRun} disabled={status === 'running'} variant="primary">
          {status === 'running' ? 'Running...' : 'Execute Backtest'}
        </Button>
      </div>

      {error && (
        <Card className="border-danger/30 text-danger text-sm font-mono">{error}</Card>
      )}

      {/* Main Interactive Indicators Chart View */}
      {ohlcv.length > 0 && (
        <Card className="p-0">
          <PriceChart data={ohlcv} theme="dark" />
        </Card>
      )}

      {/* Results View Dashboard */}
      {results && (
        <div className="space-y-8">
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-6">
            <MetricsCard
              label="Total Return"
              value={`${results.metrics.total_return_pct.toFixed(2)}%`}
              color={results.metrics.total_return >= 0 ? 'positive' : 'negative'}
            />
            <MetricsCard label="Sharpe Ratio" value={results.metrics.sharpe_ratio.toFixed(2)} />
            <MetricsCard
              label="Max Drawdown"
              value={`${(results.metrics.max_drawdown * 100).toFixed(2)}%`}
              color="negative"
            />
            <MetricsCard
              label="Win Rate"
              value={`${(results.metrics.win_rate * 100).toFixed(1)}%`}
            />
            <MetricsCard label="Profit Factor" value={results.metrics.profit_factor.toFixed(2)} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="p-0">
              <div className="p-6 pb-0">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary">
                  Equity Growth Curve
                </h3>
              </div>
              <EquityCurve data={results.equity_curve} buyHoldData={results.buy_hold_equity} />
            </Card>

            <Card className="p-0">
              <div className="p-6 pb-0">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary">
                  Drawdown Profile
                </h3>
              </div>
              <DrawdownChart data={results.equity_curve} />
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
