'use client';

import React, { Suspense, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useDataStore } from '@/stores/useDataStore';
import { useBacktestStore } from '@/stores/useBacktestStore';
import api from '@/lib/api';
import { StrategyTemplate, UserStrategy, StrategyParam } from '@/types/api';
import { TradeMarker } from '@/types/chart';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageShell } from '@/components/layout/PageShell';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { SymbolSearch } from '@/components/ui/SymbolSearch';
import { Input } from '@/components/ui/Input';
import { PerformancePanel } from '@/components/backtest/PerformancePanel';
import { MonthlyReturnsTable } from '@/components/backtest/MonthlyReturnsTable';
import { TradeStatsDist } from '@/components/backtest/TradeStatsDist';
import { TvBacktestChart } from '@/components/charts/TvBacktestChart';
import { RealismPanel } from '@/components/realism/RealismPanel';
import { safeFmt, safePct, safeSigned, safeInt, formatPrice, formatQty } from '@/lib/format';

// Parse entry_time / exit_time (number seconds OR ISO string) → unix seconds.
// Robust to both backend shapes so the chart markers survive format changes.
const toUnixSec = (v: any): number => {
  if (v == null) return 0;
  if (typeof v === 'number') return v;
  const ms = Date.parse(v);
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : 0;
};

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

function BacktestView() {
  const { symbols, ohlcv, loadSymbols, loadOHLCV } = useDataStore();
  const { runBacktest, results, status, progress, error } = useBacktestStore();

  const searchParams = useSearchParams();
  const taskParam = searchParams.get('task');
  useEffect(() => {
    if (taskParam) {
      api.getBacktestResults(taskParam)
        .then((r) => useBacktestStore.setState({ status: 'completed', results: r }))
        .catch(() => {});
    }
  }, [taskParam]);

  const [symbol, setSymbol] = useState('');
  const [timeframe, setTimeframe] = useState('1h');
  const [dataSource, setDataSource] = useState('test');
  const [startDate, setStartDate] = useState(
    new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
  );
  const [endDate, setEndDate] = useState(
    new Date().toISOString().slice(0, 10)
  );

  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [userStrategies, setUserStrategies] = useState<UserStrategy[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState('ma_cross');
  const [paramValues, setParamValues] = useState<Record<string, any>>({});

  // ── P2-2: 多幣種批量回測 ──
  const [batchInput, setBatchInput] = useState('');
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchResults, setBatchResults] = useState<
    { symbol: string; status: string; metrics?: any; error?: string }[]
  >([]);

  // ── P2-3: 回測備註 (localStorage, keyed by task_id) ──
  const [note, setNote] = useState('');
  const currentTaskId = (results as any)?.task_id ?? null;
  const noteKey = currentTaskId ? `bt_note_${currentTaskId}` : null;
  useEffect(() => {
    if (noteKey) {
      try {
        setNote(localStorage.getItem(noteKey) ?? '');
      } catch {
        setNote('');
      }
    } else {
      setNote('');
    }
  }, [noteKey]);
  const saveNote = (v: string) => {
    setNote(v);
    if (noteKey) {
      try {
        if (v) localStorage.setItem(noteKey, v);
        else localStorage.removeItem(noteKey);
      } catch {
        /* ignore */
      }
    }
  };
  const [enableFunding, setEnableFunding] = useState(false);
  const [fundingInterval, setFundingInterval] = useState(8);
  const [fundingRate, setFundingRate] = useState(0.0001);

  const [enablePerp, setEnablePerp] = useState(false);
  const [leverage, setLeverage] = useState(10);
  const [maintMargin, setMaintMargin] = useState(0.005);

  const [enableExchange, setEnableExchange] = useState(false);
  const [makerFee, setMakerFee] = useState(0.0002);
  const [takerFee, setTakerFee] = useState(0.0005);
  const [latencyBars, setLatencyBars] = useState(0);
  const [bookSlippage, setBookSlippage] = useState(0.0005);

  const [makerProbability, setMakerProbability] = useState(0);
  const [forceLimit, setForceLimit] = useState(false);

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

  // P7/P9: preselect strategy (and params) from ?strategy= / ?params= coming from /strategies or /optimize
  useEffect(() => {
    const pref = searchParams.get('strategy');
    if (!pref) return;
    const isBuiltin = templates.some((t) => t.id === pref);
    const isUser = userStrategies.some((s) => `user_${s.id}` === pref);
    if (isBuiltin || isUser) {
      setSelectedStrategy(pref);
      const incoming = searchParams.get('params');
      if (incoming) {
        try {
          const parsed = JSON.parse(decodeURIComponent(incoming)) as Record<string, any>;
          setParamValues((prev) => {
            const merged = { ...prev };
            Object.entries(parsed).forEach(([k, v]) => {
              merged[k] = typeof v === 'number' ? v : Number(v);
            });
            return merged;
          });
        } catch {
          /* ignore malformed params */
        }
      } else if (isBuiltin && Object.keys(paramValues).length === 0) {
        const t = templates.find((x) => x.id === pref);
        if (t) setParamValues(buildDefaults(t));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templates, userStrategies]);

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

  // ── TradingView-style entry/exit markers (built from results.trades) ──
  const [selectedTrade, setSelectedTrade] = useState<any>(null);

  // Highlight marker for a selected trade (from PerformancePanel or blotter)
  const highlightMarker = useMemo((): TradeMarker | null => {
    if (!selectedTrade) return null;
    const pnl = Number(selectedTrade.pnl) || 0;
    return {
      time: toUnixSec(selectedTrade.entry_time),
      position: 'belowBar',
      shape: 'arrowUp',
      color: '#f0b90b',
      text: `★ 選中`,
    };
  }, [selectedTrade]);

  const markers: TradeMarker[] = useMemo(() => {
    if (!results?.trades) return [];
    const out: TradeMarker[] = [];
    for (const t of results.trades as any[]) {
      const dir: string = t.direction || 'long';
      const isShort = dir === 'short' || dir === 'sell';
      const pnl = Number(t.pnl) || 0;
      // Entry marker
      out.push({
        time: toUnixSec(t.entry_time),
        position: 'belowBar',
        shape: isShort ? 'arrowDown' : 'arrowUp',
        color: isShort ? '#f23645' : '#089981',
        text: isShort ? '空' : '多',
      });
      // Exit marker
      out.push({
        time: toUnixSec(t.exit_time),
        position: 'aboveBar',
        shape: 'circle',
        color: pnl >= 0 ? '#089981' : '#f23645',
        text: `${(() => {
          const p = Number(t.pnl_pct);
          if (!Number.isFinite(p)) return '—';
          // pnl_pct already *100 from engine
          return `${p >= 0 ? '+' : ''}${p.toFixed(1)}%`;
        })()}`,
      });
    }
    // Append highlight marker if a trade is selected
    if (highlightMarker) {
      // Remove any existing highlight marker to avoid duplicates
      const idx = out.findIndex((m) => m.text === '★ 選中');
      if (idx >= 0) out.splice(idx, 1);
      out.push(highlightMarker);
    }
    return out;
  }, [results, highlightMarker]);

  // ── Trade Blotter sort state ──
  type SortKey = 'entry_time' | 'pnl';
  const [sortKey, setSortKey] = useState<SortKey>('entry_time');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const sortedTrades = useMemo(() => {
    const trades = [...((results?.trades as any[]) || [])];
    trades.sort((a: any, b: any) => {
      let av: number;
      let bv: number;
      if (sortKey === 'pnl') {
        av = Number(a.pnl) || 0;
        bv = Number(b.pnl) || 0;
      } else {
        av = toUnixSec(a.entry_time);
        bv = toUnixSec(b.entry_time);
      }
      return sortDir === 'asc' ? av - bv : bv - av;
    });
    return trades;
  }, [results, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const sortIndicator = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? '▲' : '▼') : '';

  const handleRun = () => {
    const paramsConfig: Record<string, any> = {};
    params.forEach((p) => {
      const raw = paramValues[p.name];
      paramsConfig[p.name] = p.type === 'choice' || p.values ? raw : Number(raw);
    });

    const payload: Record<string, any> = {
      strategy: {
        template_id: selectedStrategy,
        params: paramsConfig,
      },
      symbol,
      timeframe,
      source: dataSource,
      start_date: startDate,
      end_date: endDate,
      initial_capital: 10000.0,
      commission: 0.001,
      slippage: 0.0005,
      max_position_pct: 1.0,
    };
    // Opt-in realism — only attach when enabled (disabled = legacy 1x spot path)
    if (enableFunding) {
      payload.funding = {
        enabled: true,
        interval_hours: Number(fundingInterval),
        default_rate: Number(fundingRate),
      };
    }
    if (enablePerp) {
      payload.perpetual = {
        enabled: true,
        leverage: Number(leverage),
        maintenance_margin_rate: Number(maintMargin),
      };
    }
    if (enableExchange) {
      payload.exchange = {
        enabled: true,
        maker_fee: Number(makerFee),
        taker_fee: Number(takerFee),
        latency_bars: Number(latencyBars),
        book_base_slippage: Number(bookSlippage),
        maker_probability: Number(makerProbability),
        force_limit: forceLimit,
      };
    }

    runBacktest(payload as any);
  };

  // P2-2: 多幣種批量回測 — 併發跑每個 symbol，輪詢結果後彙總對比。
  const handleBatchRun = async () => {
    const syms = batchInput
      .split(/[\s,]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (syms.length === 0) return;
    setBatchRunning(true);
    setBatchResults(syms.map((s) => ({ symbol: s, status: 'running' })));

    const worker = async (sym: string) => {
      const payload: Record<string, any> = {
        strategy: { template_id: selectedStrategy, params: paramsConfigFor(sym) },
        symbol: sym,
        timeframe,
        source: dataSource,
        start_date: startDate,
        end_date: endDate,
        initial_capital: 10000.0,
        commission: 0.001,
        slippage: 0.0005,
        max_position_pct: 1.0,
      };
      try {
        const { task_id } = await api.runBacktest(payload as any);
        // poll until done (reuse same cadence as store)
        for (let i = 0; i < 120; i++) {
          const st = await api.getBacktestStatus(task_id);
          if (st.status === 'completed') {
            const r = await api.getBacktestResults(task_id);
            return { symbol: sym, status: 'completed', metrics: (r as any).metrics };
          }
          if (st.status === 'error') return { symbol: sym, status: 'error', error: st.error ?? 'failed' };
          await new Promise((res) => setTimeout(res, 1000));
        }
        return { symbol: sym, status: 'error', error: 'timeout' };
      } catch (e: any) {
        return { symbol: sym, status: 'error', error: e?.message ?? String(e) };
      }
    };

    const out = await Promise.all(syms.map(worker));
    setBatchResults(out);
    setBatchRunning(false);
  };

  // 依當前表單參數構建 params（與 handleRun 一致）
  const paramsConfigFor = (sym: string): Record<string, any> => {
    const cfg: Record<string, any> = {};
    params.forEach((p) => {
      const raw = paramValues[p.name];
      cfg[p.name] = p.type === 'choice' || p.values ? raw : Number(raw);
    });
    return cfg;
  };

  const exportCsv = () => {
    if (!results) return;
    const rows: string[] = [];
    const tradeCols = ['entry_time', 'exit_time', 'entry_price', 'exit_price', 'pnl', 'pnl_pct', 'size', 'side'];
    rows.push(['#', ...tradeCols].join(','));
    (results.trades as any[]).forEach((t, i) => {
      rows.push([i + 1, ...tradeCols.map((c) => JSON.stringify((t as any)[c] ?? ''))].join(','));
    });
    rows.push('');
    rows.push('equity_curve');
    (results.equity_curve as any[]).forEach((p, i) =>
      rows.push(`${i},${JSON.stringify(p.time ?? '')},${JSON.stringify(p.equity ?? '')}`)
    );
    const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `backtest_${(results as any).task_id ?? 'export'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
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
          <SymbolSearch
            label="Market Instrument"
            value={symbol}
            options={symbols.map((s) => ({ symbol: s.symbol }))}
            onChange={(s) => {
              setSymbol(s);
              const mk = symbols.find((x) => x.symbol === s);
              const src = mk?.exchange === 'bingx' ? 'bingx' : 'tradfi';
              loadOHLCV(s, timeframe, src);
            }}
          />
          <Select
            label="Timeframe"
            value={timeframe}
            onChange={(e) => {
              setTimeframe(e.target.value);
              const mk = symbols.find((x) => x.symbol === symbol);
              const src = mk?.exchange === 'bingx' ? 'bingx' : 'tradfi';
              loadOHLCV(symbol, e.target.value, src);
            }}
            options={[
              { label: '1 Minute', value: '1m' },
              { label: '5 Minutes', value: '5m' },
              { label: '15 Minutes', value: '15m' },
              { label: '30 Minutes', value: '30m' },
              { label: '45 Minutes', value: '45m' },
              { label: '1 Hour', value: '1h' },
              { label: '4 Hours', value: '4h' },
              { label: '1 Day', value: '1d' },
            ]}
          />
          <Select
            label="Data Source"
            value={dataSource}
            onChange={(e) => setDataSource(e.target.value)}
            options={[
              { label: 'Test (local, instant)', value: 'test' },
              { label: 'Live (BingX)', value: 'bingx' },
            ]}
          />
          <Select
            label="Strategy"
            value={selectedStrategy}
            onChange={(e) => handleStrategyChange(e.target.value)}
            options={strategyOptions}
          />
          <Input
            label="Start Date"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
          <Input
            label="End Date"
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
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

        <RealismPanel
          state={{
            enableFunding, fundingInterval, fundingRate,
            enablePerp, leverage, maintMargin,
            enableExchange, makerFee, takerFee, latencyBars, bookSlippage,
            makerProbability, forceLimit,
          }}
          handlers={{
            setEnableFunding, setFundingInterval, setFundingRate,
            setEnablePerp, setLeverage, setMaintMargin,
            setEnableExchange, setMakerFee, setTakerFee, setLatencyBars, setBookSlippage,
            setMakerProbability, setForceLimit,
          }}
        />

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-t border-border/10 pt-4">
          <div className="text-sm font-mono text-textSecondary">
            {status === 'running' ? `Backtesting Progress: ${Math.round(progress)}%` : 'Ready'}
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={handleRun} disabled={status === 'running'} variant="primary">
              {status === 'running' ? 'Running...' : 'Execute Backtest'}
            </Button>
            {results && (
              <Button variant="ghost" onClick={exportCsv}>Export CSV</Button>
            )}
          </div>
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
          <TvBacktestChart
            data={ohlcv}
            markers={markers}
            equityData={results?.equity_curve ?? []}
            buyHoldData={results?.buy_hold_equity ?? []}
            emaLen={200}
            theme="dark"
          />
        </Card>
      )}

      {/* P2-2: 多幣種批量回測 */}
      <Card>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-textSecondary">
            多幣種批量回測
          </h2>
          <span className="font-mono text-xs text-textSecondary">
            逗號或空白分隔 · 共用當前策略參數
          </span>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Input
            label="Symbols"
            placeholder="BTCUSDT, ETHUSDT, SOLUSDT"
            value={batchInput}
            onChange={(e) => setBatchInput(e.target.value)}
          />
          <Button
            onClick={handleBatchRun}
            disabled={batchRunning}
            variant="primary"
            className="mt-6"
          >
            {batchRunning ? '批次執行中...' : '批次回測'}
          </Button>
        </div>

        {batchResults.length > 0 && (
          <div className="mt-5 overflow-x-auto">
            <table className="w-full text-sm font-mono">
              <thead>
                <tr className="text-left text-xs uppercase text-textSecondary border-b border-border/10">
                  <th className="px-4 py-2">Symbol</th>
                  <th className="px-4 py-2 text-right">總回報%</th>
                  <th className="px-4 py-2 text-right">交易數</th>
                  <th className="px-4 py-2 text-right">勝率%</th>
                  <th className="px-4 py-2 text-right">最大回撤%</th>
                  <th className="px-4 py-2 text-right">獲利因子</th>
                  <th className="px-4 py-2 text-right">年化%</th>
                  <th className="px-4 py-2">狀態</th>
                </tr>
              </thead>
              <tbody>
                {batchResults.map((r) => (
                  <tr key={r.symbol} className="border-t border-border/10">
                    <td className="px-4 py-2 font-semibold text-text">{r.symbol}</td>
                    {r.status === 'completed' && r.metrics ? (
                      <>
                        <td className={`px-4 py-2 text-right tabular-nums ${Number(r.metrics.total_return_pct) >= 0 ? 'text-[#089981]' : 'text-[#f23645]'}`}>
                          {safePct(Number(r.metrics.total_return_pct))}
                        </td>
                        <td className="px-4 py-2 text-right text-text tabular-nums">{r.metrics.total_trades ?? '—'}</td>
                        <td className="px-4 py-2 text-right text-text tabular-nums">
                          {safePct(Number(r.metrics.win_rate), { signed: false })}
                        </td>
                        <td className="px-4 py-2 text-right text-text tabular-nums">
                          {safePct(Number(r.metrics.max_drawdown_pct), { signed: false })}
                        </td>
                        <td className="px-4 py-2 text-right text-text tabular-nums">
                          {safeFmt(Number(r.metrics.profit_factor))}
                        </td>
                        <td className={`px-4 py-2 text-right tabular-nums ${Number(r.metrics.annual_return_pct) >= 0 ? 'text-[#089981]' : 'text-[#f23645]'}`}>
                          {safePct(Number(r.metrics.annual_return_pct))}
                        </td>
                      </>
                    ) : (
                      <td className="px-4 py-2 text-right text-textSecondary" colSpan={6}>
                        {r.status === 'running' ? '執行中...' : r.error ?? r.status}
                      </td>
                    )}
                    <td className="px-4 py-2 text-textSecondary">{r.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Results */}
      {status === 'completed' && results && (results.trades ?? []).length > 0 ? (
        <div className="space-y-6">
          {/* Result summary: strategy + symbol + timeframe */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-border/40 bg-surface/50 px-4 py-3 text-sm">
            <span className="text-textSecondary">回測配置</span>
            <span className="rounded bg-accent/10 px-2 py-0.5 font-medium text-accent">
              {(() => {
                const tid = results?.config?.strategy?.template_id || selectedStrategy;
                const t = templates.find((x) => x.id === tid);
                return t?.name ?? tid ?? '—';
              })()}
            </span>
            <span className="font-mono text-text">{results?.config?.symbol ?? symbol}</span>
            <span className="rounded bg-border/20 px-2 py-0.5 text-textSecondary">
              {results?.config?.timeframe ?? timeframe}
            </span>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
            <span className="text-xs font-mono text-textSecondary">備註</span>
            <input
              className="flex-1 rounded border border-border/30 bg-surface px-3 py-1.5 text-sm text-text outline-none focus:border-accent"
              placeholder={noteKey ? '為此回測加入備註（本機保存）' : '回測完成後可加備註'}
              value={note}
              disabled={!noteKey}
              onChange={(e) => saveNote(e.target.value)}
            />
            {noteKey && (
              <span className="font-mono text-[10px] text-textSecondary">已存本機 · {noteKey}</span>
            )}
          </div>
        </div>

        <Card className="p-0 overflow-hidden">
            <div className="p-6 pb-0">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary">
                績效面板
              </h3>
            </div>
            <PerformancePanel
              metrics={results.metrics}
              equity={results.equity_curve}
              buyHold={results.buy_hold_equity}
              trades={results.trades}
              positionStatus={results.position_status}
              initialCapital={Number(results.config?.initial_capital ?? 100000)}
              onSelectTrade={setSelectedTrade}
            />
          </Card>

          {/* Trade blotter */}
          {results.trades && results.trades.length > 0 && (
            <Card className="p-0 overflow-hidden">
              <div className="flex items-center justify-between p-6 pb-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary">
                  Trade Blotter
                </h3>
                <span className="text-xs font-mono text-textSecondary">
                  {results.trades.length} fills
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm font-mono">
                  <thead>
                    <tr className="text-left text-xs uppercase text-textSecondary border-t border-border/10">
                      <th className="px-6 py-3">#</th>
                      <th
                        className="px-6 py-3 cursor-pointer select-none hover:text-text"
                        onClick={() => toggleSort('entry_time')}
                      >
                        Entry Time {sortIndicator('entry_time')}
                      </th>
                      <th className="px-6 py-3">Side</th>
                      <th className="px-6 py-3 text-right">Entry</th>
                      <th className="px-6 py-3 text-right">Exit</th>
                      <th className="px-6 py-3 text-right">Size</th>
                      <th
                        className="px-6 py-3 text-right cursor-pointer select-none hover:text-text"
                        onClick={() => toggleSort('pnl')}
                      >
                        PnL {sortIndicator('pnl')}
                      </th>
                      <th className="px-6 py-3 text-right">PnL %</th>
                      <th className="px-6 py-3">Exit Reason</th>
                      <th className="px-6 py-3 text-right">Bars</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedTrades.map((t: any, i: number) => (
                      <tr
                        key={i}
                        className={`border-t border-[#363c4e]/10 transition-colors duration-150 cursor-pointer ${
                          selectedTrade?.trade_id === t.trade_id
                            ? 'bg-[#089981]/5'
                            : 'hover:bg-white/[0.02]'
                        }`}
                        onClick={() => setSelectedTrade(selectedTrade?.trade_id === t.trade_id ? null : t)}
                      >
                        <td className="px-6 py-3 text-textSecondary tabular-nums">{i + 1}</td>
                        <td className="px-6 py-3 text-textSecondary">{t.entry_time}</td>
                        <td className={`px-6 py-3 font-semibold ${
                          t.direction === 'short' ? 'text-[#f23645]' : 'text-[#089981]'
                        }`}>
                          {t.direction === 'short' ? '空' : '多'}
                        </td>
                        <td className="px-6 py-3 text-right text-text tabular-nums">
                          {formatPrice(t.entry_price)}
                        </td>
                        <td className="px-6 py-3 text-right text-text tabular-nums">
                          {t.exit_price != null ? formatPrice(t.exit_price) : '—'}
                        </td>
                        <td className="px-6 py-3 text-right text-textSecondary tabular-nums">
                          {formatQty((t as any).size ?? (t as any).quantity)}
                        </td>
                        <td
                          className={`px-6 py-3 text-right font-semibold tabular-nums ${
                            Number(t.pnl) >= 0 ? 'text-[#089981]' : 'text-[#f23645]'
                          }`}
                        >
                          {safeSigned(Number(t.pnl))}
                        </td>
                        <td
                          className={`px-6 py-3 text-right tabular-nums ${
                            Number(t.pnl_pct) >= 0 ? 'text-[#089981]' : 'text-[#f23645]'
                          }`}
                        >
                          {t.pnl_pct != null ? safePct(Number(t.pnl_pct)) : '—'}
                        </td>
                        <td className="px-6 py-3 text-textSecondary">{t.exit_reason || '—'}</td>
                        <td className="px-6 py-3 text-right text-textSecondary tabular-nums">
                          {t.holding_bars != null ? safeInt(Number(t.holding_bars)) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* P1-2: 月度收益表 */}
          {results.equity_curve && results.equity_curve.length > 0 && (
            <Card className="p-0 overflow-hidden">
              <div className="p-6 pb-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary">
                  月度收益表
                </h3>
              </div>
              <MonthlyReturnsTable
                equity={results.equity_curve}
                initialCapital={Number(results.config?.initial_capital ?? 10000)}
              />
            </Card>
          )}

          {/* P1-3: 交易統計分佈 */}
          {results.trades && results.trades.length > 0 && (
            <Card className="p-0 overflow-hidden">
              <div className="p-6 pb-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary">
                  交易統計分佈
                </h3>
              </div>
              <div className="px-6 pb-6">
                <TradeStatsDist trades={results.trades} />
              </div>
            </Card>
          )}
        </div>
      ) : status === 'completed' ? (
        <Card><EmptyState title="No trades generated" description="The strategy produced no entries for this configuration. Try widening parameter bounds or a different symbol." /></Card>
      ) : null}
    </PageShell>
  );
}

export default function BacktestPage() {
  return (
    <Suspense fallback={null}>
      <BacktestView />
    </Suspense>
  );
}
