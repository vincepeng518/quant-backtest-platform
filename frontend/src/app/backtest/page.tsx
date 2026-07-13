'use client';

import React, { useEffect, useState } from 'react';
import { useDataStore } from '@/stores/useDataStore';
import { useBacktestStore } from '@/stores/useBacktestStore';
import api from '@/lib/api';
import { StrategyTemplate, UserStrategy, StrategyParam } from '@/types/api';
import { Card } from '@/components/ui/Card';
import { PageShell } from '@/components/layout/PageShell';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Input } from '@/components/ui/Input';
import { MetricsCard } from '@/components/backtest/MetricsCard';
import { PriceChart } from '@/components/charts/PriceChart';
import { EquityCurve } from '@/components/charts/EquityCurve';
import { DrawdownChart } from '@/components/charts/DrawdownChart';

// Local view of the backend param spec (backend sends {type, min, max, step}
// for ranges and {type, values} for choices). The shared StrategyParam type
// doesn't carry these fields, so we model them here.
interface ParamSpec {
  name: string;
  type: 'range' | 'choice' | string;
  min?: number;
  max?: number;
  step?: number;
  values?: string[];
}

export default function BacktestPage() {
  const { symbols, ohlcv, loadSymbols, loadOHLCV } = useDataStore();
  const { runBacktest, results, status, progress, error } = useBacktestStore();

  const [symbol, setSymbol] = useState('');
  const [timeframe, setTimeframe] = useState('1h');

  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [userStrategies, setUserStrategies] = useState<UserStrategy[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState('ma_cross');
  const [paramValues, setParamValues] = useState<Record<string, any>>({});

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

  useEffect(() => {
    api.getTemplates().then(setTemplates);
    api.listUserStrategies().then(setUserStrategies);
  }, []);

  const buildDefaults = (t?: StrategyTemplate): Record<string, any> => {
    const d: Record<string, any> = {};
    const params = (t?.params as unknown as ParamSpec[]) || [];
    params.forEach((p) => {
      if (p.type === 'choice' || p.values) {
        d[p.name] = p.values?.[0] ?? '';
      } else {
        d[p.name] = p.min ?? 0;
      }
    });
    return d;
  };

  // Seed defaults for the initial strategy once templates arrive.
  useEffect(() => {
    if (templates.length > 0 && Object.keys(paramValues).length === 0) {
      const t = templates.find((x) => x.id === selectedStrategy);
      if (t) setParamValues(buildDefaults(t));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templates]);

  const handleStrategyChange = (value: string) => {
    setSelectedStrategy(value);
    const t = templates.find((x) => x.id === value);
    setParamValues(buildDefaults(t));
  };

  const selectedTemplate = templates.find((t) => t.id === selectedStrategy);
  const params = (selectedTemplate?.params as unknown as ParamSpec[]) || [];

  const handleRun = () => {
    const paramsConfig: Record<string, any> = {};
    params.forEach((p) => {
      const raw = paramValues[p.name];
      paramsConfig[p.name] = p.type === 'choice' || p.values ? raw : Number(raw);
    });

    runBacktest({
      strategy: {
        template_id: selectedStrategy,
        params: paramsConfig,
      },
      symbol,
      timeframe,
      from: Math.floor(Date.now() / 1000) - 365 * 24 * 60 * 60,
      to: Math.floor(Date.now() / 1000),
      risk: {
        initial_capital: 10000.0,
        commission: 0.001,
        slippage: 0.0005,
        max_position_pct: 1.0,
      },
    });
  };

  const builtinOptions = templates
    .filter((t) => !t.id.startsWith('user_'))
    .map((t) => ({ label: t.name, value: t.id }));
  const userOptions = userStrategies.map((s) => ({
    label: `我的：${s.name}`,
    value: `user_${s.id}`,
  }));
  const strategyOptions = [...builtinOptions, ...userOptions];

  return (
    <PageShell
      eyebrow="Backtest / workflow"
      title="策略回測"
      subtitle="載入市場數據，套用技術策略或你上傳的自定義策略，秒級生成績效報告與權益曲線。"
    >
      {/* Configuration Card */}
      <Card>
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-textSecondary">
            策略配置
          </h2>
          <span className="font-mono text-xs text-textSecondary">
            {selectedTemplate?.name || selectedStrategy}
          </span>
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
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
          <Select
            label="Strategy"
            value={selectedStrategy}
            onChange={(e) => handleStrategyChange(e.target.value)}
            options={strategyOptions}
          />

          {params.map((p) =>
            p.type === 'choice' || p.values ? (
              <Select
                key={p.name}
                label={p.name}
                value={paramValues[p.name] ?? ''}
                onChange={(e) =>
                  setParamValues({ ...paramValues, [p.name]: e.target.value })
                }
                options={(p.values || []).map((v) => ({ label: v, value: v }))}
              />
            ) : (
              <Input
                key={p.name}
                label={p.name}
                type="number"
                value={paramValues[p.name] ?? ''}
                min={p.min}
                max={p.max}
                step={p.step}
                onChange={(e) =>
                  setParamValues({ ...paramValues, [p.name]: e.target.value })
                }
              />
            )
          )}
        </div>

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-t border-border/10 pt-4">
          <div className="text-sm font-mono text-textSecondary">
            {status === 'running' ? `Backtesting Progress: ${Math.round(progress)}%` : 'Ready'}
          </div>
          <Button onClick={handleRun} disabled={status === 'running'} variant="primary">
            {status === 'running' ? 'Running...' : 'Execute Backtest'}
          </Button>
        </div>

        {error && (
          <p className="mt-3 text-sm font-mono text-danger">{error}</p>
        )}
      </Card>

      {/* Price Chart */}
      {ohlcv.length > 0 && (
        <Card className="p-0 overflow-hidden">
          <div className="p-6 pb-0">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary">
              Price Action
            </h3>
          </div>
          <PriceChart data={ohlcv} theme="dark" />
        </Card>
      )}

      {/* Results */}
      {results && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
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

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card className="p-0 overflow-hidden">
              <div className="p-6 pb-0">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary">
                  Equity Growth Curve
                </h3>
              </div>
              <EquityCurve data={results.equity_curve} buyHoldData={results.buy_hold_equity} />
            </Card>

            <Card className="p-0 overflow-hidden">
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
    </PageShell>
  );
};
