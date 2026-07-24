'use client';

import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { PageShell } from '@/components/layout/PageShell';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { api } from '@/lib/api';

interface TradeRec {
  symbol?: string;
  side?: string;
  positionAmt?: number;
  qty?: number;
  avgPrice?: number;
  exitPrice?: number;
  leverage?: number | null;
  unrealizedProfit?: number;
  realizedProfit?: number;
  pnlRatio?: number;
  positionValue?: number;
  notional?: number;
  margin?: number;
  liquidationPrice?: number;
  fee?: number;
  fundingFee?: number;
  status?: string;
  ts?: number;
  closeTime?: number;
  holdDuration?: number;
  _snapshot?: string;
}

type Range = 'all' | 'month' | 'day';

function pnlOf(r: TradeRec): number {
  return Number(r.realizedProfit ?? 0) + Number(r.unrealizedProfit ?? 0);
}

function fmt(n: number, d = 2): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}

// 動態精度: 價格越大精度越低, 越小精度越高
function fmtPrice(n: number | undefined | null): string {
  if (n == null) return '—';
  const a = Math.abs(n);
  if (a >= 1000) return fmt(n, 2);
  if (a >= 1) return fmt(n, 4);
  if (a >= 0.01) return fmt(n, 5);
  return fmt(n, 6);
}

function fmtQty(n: number | undefined | null): string {
  if (n == null) return '—';
  const a = Math.abs(n);
  if (a >= 100) return fmt(n, 2);
  if (a >= 1) return fmt(n, 4);
  return fmt(n, 6);
}

function fmtDuration(ms: number | undefined | null): string {
  if (ms == null || ms <= 0) return '—';
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h${m % 60 ? ` ${m % 60}m` : ''}`;
  const d = Math.floor(h / 24);
  return `${d}d${h % 24 ? ` ${h % 24}h` : ''}`;
}

// BingX symbol 簡化 (與 bot 規則同步) — 防禦層, 避免後端漏簡化
function simplifySymbol(raw: string | undefined | null): string {
  if (!raw) return raw ?? '';
  let s = raw.trim().replace(':USDT', '').replace(':USDC', '');
  // 外匯: NCFX<BASE>2<QUOTE>-USDT → BASE/QUOTE
  let m = s.match(/^NCFX(\w+?)2(\w+)-USDT$/);
  if (m) return `${m[1]}/${m[2]}`;
  // 商品/股票/股指: NC{CO|SK|SI}[數字]<NAME>2USD-USDT → NAME (前導數字去掉)
  m = s.match(/^NC(CO|SK|SI)\d*(.+?)2USD-USDT$/);
  if (m) return m[2];
  // TradFi 變體: NC<NAME>-USDT → NAME (無 2USD 後綴, 例 NCOILWTI-USDT → OILWTI)
  m = s.match(/^NC(\w+)-USDT$/);
  if (m) return m[1];
  // Crypto: 去尾部 -USDT
  if (s.endsWith('-USDT')) return s.slice(0, -5);
  return s;
}

// journalit 風格: 盈虧 -> 綠/紅階層 class
function heatClass(pnl: number): string {
  if (pnl === 0) return 'heat-empty';
  const a = Math.abs(pnl);
  let lvl = 1;
  if (a > 50) lvl = 4;
  else if (a > 20) lvl = 3;
  else if (a > 5) lvl = 2;
  return pnl > 0 ? `heat-profit-${lvl}` : `heat-loss-${lvl}`;
}

export default function TradesPage() {
  const [source, setSource] = useState<'bingx' | 'arb' | 'predict'>('bingx');
  const [records, setRecords] = useState<TradeRec[]>([]);
  const [metrics, setMetrics] = useState<any>(null);
  const [feesTotal, setFeesTotal] = useState<number | null>(null);
  const [fundingTotal, setFundingTotal] = useState<number | null>(null);
  const [metrics30d, setMetrics30d] = useState<Record<string, number> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<Range>('all');
  const [heartbeat, setHeartbeat] = useState<{ alive: boolean; updated_at: string | null } | null>(null);

  useEffect(() => {
    if (source !== 'predict') return;
    api.getPredictHeartbeat()
      .then((d: any) => setHeartbeat({ alive: d.alive, updated_at: d.updated_at }))
      .catch(() => setHeartbeat({ alive: false, updated_at: null }));
  }, [source]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const fetcher = source === 'arb' ? api.getArbTrades() : source === 'predict' ? api.getPredictTrades() : api.getTrades();
    fetcher
      .then((d: any) => {
        setRecords(d.records ?? []);
        setMetrics(d.metrics ?? null);
        setFeesTotal(d.fees_total ?? null);
        setFundingTotal(d.funding_total ?? null);
        setMetrics30d(d.metrics_30d ?? null);
      })
      .catch((e) => setError(e?.message ?? 'failed to load trades'))
      .finally(() => setLoading(false));
  }, [source]);

  const now = Date.now();
  // 從 _snapshot 檔名解析時間 (fallback, 格式 trades_YYYYMMDD_HHMMSS.json)
  const snapTs = (r: TradeRec): number => {
    const f = r._snapshot || '';
    const m = f.match(/(\d{8})_(\d{6})/);
    if (m) {
      const [y, mo, d] = [m[1].slice(0, 4), m[1].slice(4, 6), m[1].slice(6, 8)];
      const [hh, mm, ss] = [m[2].slice(0, 2), m[2].slice(2, 4), m[2].slice(4, 6)];
      const t = Date.parse(`${y}-${mo}-${d}T${hh}:${mm}:${ss}Z`);
      if (!Number.isNaN(t)) return t;
    }
    return 0;
  };
  const sortKey = (r: TradeRec): number => {
    const t = r.ts ?? 0;
    return t > 0 ? t : snapTs(r);
  };
  const filtered = useMemo(() => {
    let list = records;
    if (range !== 'all') {
      list = records.filter((r) => {
        const t = sortKey(r) / 1000;
        const diff = now / 1000 - t;
        if (range === 'day') return diff <= 86400;
        if (range === 'month') return diff <= 86400 * 30;
        return true;
      });
    }
    // 開倉時間降冪: 新的在上 (ts 為毫秒, fallback 檔名時間)
    return [...list].sort((a, b) => sortKey(b) - sortKey(a));
  }, [records, range, now]);

  const stats = useMemo(() => {
    let totalPnl = 0, totalPos = 0, wins = 0, losses = 0, scr = 0;
    let longPnl = 0, shortPnl = 0;
    let streak = 0, maxWinStreak = 0, maxLossStreak = 0;
    // 按 ts 排序算連續 (升冪)
    const sorted = [...filtered].sort((a, b) => sortKey(a) - sortKey(b));
    for (const r of sorted) {
      const p = pnlOf(r);
      totalPnl += p;
      totalPos += Number(r.positionValue ?? 0);
      if (p > 0) { wins++; streak = streak > 0 ? streak + 1 : 1; maxWinStreak = Math.max(maxWinStreak, streak); }
      else if (p < 0) { losses++; streak = streak < 0 ? streak - 1 : -1; maxLossStreak = Math.max(maxLossStreak, -streak); }
      else scr++;
      const s = String(r.side ?? '').toUpperCase();
      if (s.includes('LONG')) longPnl += p;
      else if (s.includes('SHORT')) shortPnl += p;
    }
    const closed = wins + losses;
    const winRate = closed > 0 ? (wins / closed) * 100 : 0;
    const avgPnl = closed > 0 ? totalPnl / closed : 0;
    return { totalPnl, totalPos, wins, losses, scr, winRate, avgPnl, longPnl, shortPnl, maxWinStreak, maxLossStreak };
  }, [filtered]);

  // PnL Calendar Heatmap (journalit 風格)
  const heatmap = useMemo(() => {
    const dayMap = new Map<string, number>();
    for (const r of filtered) {
      const t = sortKey(r) / 1000;
      if (!t) continue;
      const d = new Date(t * 1000);
      const key = d.toISOString().slice(0, 10);
      dayMap.set(key, (dayMap.get(key) ?? 0) + pnlOf(r));
    }
    // 產生近 12 週格子 (從今天往前)
    const days = [];
    const today = new Date();
    for (let i = 83; i >= 0; i--) { // 12週*7
      const dt = new Date(today);
      dt.setDate(dt.getDate() - i);
      const key = dt.toISOString().slice(0, 10);
      days.push({ key, pnl: dayMap.get(key) ?? 0, dow: dt.getDay() });
    }
    return days;
  }, [filtered]);

  const tabs: { key: Range; label: string }[] = [
    { key: 'all', label: '全部' },
    { key: 'month', label: '月' },
    { key: 'day', label: '日' },
  ];

  return (
    <PageShell
      eyebrow="Trades / journal"
      title="交易記錄"
      subtitle="自動抓取 BingX 持倉與歷史已平倉，永久保存於 GitHub。僅含客觀數據。"
    >
      <div className="flex items-center justify-between mb-4">
        <Link href="/history" className="text-xs font-mono text-accent hover:underline">回測歷史 ↗</Link>
      </div>
      {/* 來源切換: BingX / Arb Bot / Predict.fun */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {([
          { key: 'bingx', label: 'BingX 紀錄' },
          { key: 'arb', label: 'Arb Bot' },
          { key: 'predict', label: 'Predict.fun' },
        ] as const).map((s) => (
          <button
            key={s.key}
            onClick={() => setSource(s.key)}
            className={`px-3 py-1.5 rounded-md text-sm font-mono transition-colors ${
              source === s.key ? 'bg-accent text-background font-medium' : 'bg-surface text-textSecondary hover:text-text'
            }`}
          >
            {s.label}
          </button>
        ))}
        {source === 'predict' && heartbeat && (
          <span className={`ml-2 px-2 py-1 rounded text-xs font-mono ${
            heartbeat.alive ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
          }`}>
            {heartbeat.alive ? '● ALIVE' : '● DEAD'}
            {heartbeat.updated_at && (
              <span className="ml-1 opacity-70">
                {new Date(heartbeat.updated_at).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </span>
        )}
      </div>
      {/* 範圍切換 */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setRange(t.key)}
            className={`px-3 py-1.5 rounded-md text-sm font-mono transition-colors ${
              range === t.key ? 'bg-accent text-background font-medium' : 'bg-surface text-textSecondary hover:text-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 統計卡 (journalit 風格擴充) — 僅在有資料時顯示 */}
      {records.length > 0 && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">P/L ({range === 'all' ? '全部' : range === 'month' ? '近30日' : '近24h'})</p>
              <p className={`text-xl font-mono font-semibold ${stats.totalPnl >= 0 ? 'text-accent' : 'text-danger'}`}>
                {stats.totalPnl >= 0 ? '+' : ''}{fmt(stats.totalPnl)}
              </p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">勝率 / 筆數</p>
              <p className="text-xl font-mono font-semibold text-text">{fmt(stats.winRate, 1)}%</p>
              <p className="text-xs text-textSecondary font-mono">{stats.wins}W / {stats.losses}L / {stats.scr}平</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">平均盈虧</p>
              <p className={`text-xl font-mono font-semibold ${stats.avgPnl >= 0 ? 'text-accent' : 'text-danger'}`}>
                {stats.avgPnl >= 0 ? '+' : ''}{fmt(stats.avgPnl)}
              </p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">總倉位大小</p>
              <p className="text-xl font-mono font-semibold text-text">{fmt(stats.totalPos)}</p>
            </Card>
          </div>

          {/* 官方風格 30d 統計 (對齊 BingX 交易分析) */}
          {metrics30d && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <Card className="p-4">
                <p className="text-xs text-textSecondary font-mono mb-1">已實現盈虧 (30d)</p>
                <p className={`text-xl font-mono font-semibold ${(metrics30d.pnl ?? 0) >= 0 ? 'text-accent' : 'text-danger'}`}>
                  {(metrics30d.pnl ?? 0) >= 0 ? '+' : ''}{fmt(metrics30d.pnl ?? 0)}
                </p>
              </Card>
              <Card className="p-4">
                <p className="text-xs text-textSecondary font-mono mb-1">交易額/總倉位 (30d)</p>
                <p className="text-xl font-mono font-semibold text-text">{fmt(metrics30d.total_notional ?? 0)}</p>
              </Card>
              <Card className="p-4">
                <p className="text-xs text-textSecondary font-mono mb-1">勝率 (30d)</p>
                <p className="text-xl font-mono font-semibold text-text">{fmt(metrics30d.win_rate ?? 0, 1)}%</p>
                <p className="text-xs text-textSecondary font-mono">{metrics30d.wins}W / {metrics30d.losses}L</p>
              </Card>
              <Card className="p-4">
                <p className="text-xs text-textSecondary font-mono mb-1">盈利 / 虧損金額</p>
                <p className="text-sm font-mono">
                  <span className="text-accent">+{fmt(metrics30d.profit_amount ?? 0)}</span>
                  {' / '}
                  <span className="text-danger">{fmt(metrics30d.loss_amount ?? 0)}</span>
                </p>
              </Card>
            </div>
          )}

          {/* 手續費 + 資金費用 (另計, 不併入 P/L) */}
          {feesTotal != null && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <Card className="p-4">
                <p className="text-xs text-textSecondary font-mono mb-1">手續費 (Fees)</p>
                <p className="text-xl font-mono font-semibold text-danger">-{fmt(feesTotal)}</p>
              </Card>
              <Card className="p-4">
                <p className="text-xs text-textSecondary font-mono mb-1">資金費用 (Funding)</p>
                <p className={`text-xl font-mono font-semibold ${(fundingTotal ?? 0) >= 0 ? 'text-accent' : 'text-danger'}`}>
                  {(fundingTotal ?? 0) >= 0 ? '+' : ''}{fmt(fundingTotal ?? 0)}
                </p>
              </Card>
            </div>
          )}

          {/* 多空 + 連續 (第二排) */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">多頭 P/L</p>
              <p className={`text-lg font-mono font-semibold ${stats.longPnl >= 0 ? 'text-accent' : 'text-danger'}`}>
                {stats.longPnl >= 0 ? '+' : ''}{fmt(stats.longPnl)}
              </p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">空頭 P/L</p>
              <p className={`text-lg font-mono font-semibold ${stats.shortPnl >= 0 ? 'text-accent' : 'text-danger'}`}>
                {stats.shortPnl >= 0 ? '+' : ''}{fmt(stats.shortPnl)}
              </p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">最大連續盈利</p>
              <p className="text-lg font-mono font-semibold text-accent">{stats.maxWinStreak} 筆</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">最大連續虧損</p>
              <p className="text-lg font-mono font-semibold text-danger">{stats.maxLossStreak} 筆</p>
            </Card>
          </div>

          {/* 專業績效指標 (借 awesome-quant/empyrical 算法) */}
          <div className="grid grid-cols-3 md:grid-cols-6 gap-3 mb-6">
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">Sharpe</p>
              <p className="text-xl font-mono font-semibold text-text">{metrics?.sharpe ?? '—'}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">Sortino</p>
              <p className="text-xl font-mono font-semibold text-text">{metrics?.sortino ?? '—'}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">Calmar</p>
              <p className="text-xl font-mono font-semibold text-text">{metrics?.calmar ?? '—'}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">年化報酬</p>
              <p className="text-xl font-mono font-semibold text-text">{metrics?.annual_return != null ? fmt(metrics.annual_return) : '—'}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">最大回撤</p>
              <p className="text-xl font-mono font-semibold text-danger">{metrics?.max_drawdown != null ? fmt(metrics.max_drawdown) : '—'}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">Profit Factor</p>
              <p className="text-xl font-mono font-semibold text-accent">{metrics?.profit_factor ?? '—'}</p>
            </Card>
          </div>

          {/* PnL Calendar Heatmap (journalit ContributionsHeatmap 風格) */}
          <Card className="p-4 mb-6">
            <p className="text-xs text-textSecondary font-mono mb-3">PnL 日曆 (近 12 週, 綠=盈/紅=虧)</p>
            <div className="flex flex-wrap gap-1">
              {heatmap.map((d) => (
                <div
                  key={d.key}
                  className={`heat-cell ${heatClass(d.pnl)}`}
                  title={`${d.key}: ${d.pnl >= 0 ? '+' : ''}${fmt(d.pnl)}`}
                />
              ))}
            </div>
            <div className="flex items-center gap-2 mt-3 text-xs font-mono text-textSecondary">
              <span>少</span>
              <span className="heat-cell heat-empty" />
              <span className="heat-cell heat-loss-2" />
              <span className="heat-cell heat-loss-4" />
              <span className="heat-cell heat-profit-2" />
              <span className="heat-cell heat-profit-4" />
              <span>多</span>
            </div>
          </Card>
        </>
      )}

      {/* 交易表格 */}
      <Card className="min-h-[300px]">
        {loading ? (
          <div className="flex justify-center py-12"><Spinner size="lg" /></div>
        ) : error ? (
          <p className="text-sm font-mono text-danger p-6">{error}</p>
        ) : records.length === 0 ? (
          <EmptyState title="No trades yet" description={source === 'arb' ? "Arb bot 尚未成交 (DRY_RUN 或無套利信號)。" : source === 'predict' ? "Predict.fun 15m BTC/ETH 預測市場尚無持倉。" : "Run bot/trade_bot.py to capture BingX data."} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-mono">
              <thead>
                <tr className="text-textSecondary text-xs border-b border-border/20">
                  <th className="text-left px-3 py-2">Symbol</th>
                  <th className="text-left px-3 py-2">Side</th>
                  <th className="text-right px-3 py-2">Qty</th>
                  <th className="text-right px-3 py-2">開倉價</th>
                  <th className="text-right px-3 py-2">平倉價</th>
                  <th className="text-right px-3 py-2">槓桿</th>
                  <th className="text-right px-3 py-2">名義</th>
                  <th className="text-right px-3 py-2">盈虧</th>
                  <th className="text-right px-3 py-2">費用</th>
                  <th className="text-left px-3 py-2">開倉</th>
                  <th className="text-left px-3 py-2">平倉</th>
                  <th className="text-left px-3 py-2">持倉</th>
                  <th className="text-left px-3 py-2">狀態</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r, i) => {
                  const p = pnlOf(r);
                  const fee = Number(r.fee ?? 0) + Number(r.fundingFee ?? 0);
                  const openTs = sortKey(r);
                  const closeTs = r.closeTime ?? 0;
                  return (
                    <tr key={i} className="border-b border-border/10 hover:bg-surface/40">
                      <td className="px-3 py-2 text-text">{simplifySymbol(r.symbol)}</td>
                      <td className="px-3 py-2 text-textSecondary">{r.side}</td>
                      <td className="px-3 py-2 text-right text-textSecondary">{fmtQty(r.qty ?? r.positionAmt)}</td>
                      <td className="px-3 py-2 text-right text-text">{fmtPrice(r.avgPrice)}</td>
                      <td className="px-3 py-2 text-right text-text">{fmtPrice(r.exitPrice)}</td>
                      <td className="px-3 py-2 text-right text-textSecondary">{r.leverage != null ? `${r.leverage}x` : '—'}</td>
                      <td className="px-3 py-2 text-right text-text">{r.notional ? fmt(r.notional) : (r.positionValue ? fmt(r.positionValue) : '—')}</td>
                      <td className={`px-3 py-2 text-right ${p >= 0 ? 'text-accent' : 'text-danger'}`}>
                        {p >= 0 ? '+' : ''}{fmt(p)}
                      </td>
                      <td className="px-3 py-2 text-right text-danger">{fee !== 0 ? `-${fmt(Math.abs(fee), 4)}` : '—'}</td>
                      <td className="px-3 py-2 text-textSecondary">
                        {openTs ? new Date(openTs).toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'}
                      </td>
                      <td className="px-3 py-2 text-textSecondary">
                        {closeTs ? new Date(closeTs).toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'}
                      </td>
                      <td className="px-3 py-2 text-textSecondary">{fmtDuration(r.holdDuration)}</td>
                      <td className="px-3 py-2 text-textSecondary">{r.status}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <style jsx>{`
        .heat-cell {
          width: 11px; height: 11px; border-radius: 2px;
          background: rgba(var(--border-rgb, 55, 53, 47), 0.12);
        }
        .heat-empty { background: rgba(120, 120, 120, 0.15); }
        .heat-profit-1 { background: rgba(16, 185, 129, 0.25); }
        .heat-profit-2 { background: rgba(16, 185, 129, 0.45); }
        .heat-profit-3 { background: rgba(16, 185, 129, 0.70); }
        .heat-profit-4 { background: rgba(5, 150, 105, 0.90); }
        .heat-loss-1 { background: rgba(239, 68, 68, 0.25); }
        .heat-loss-2 { background: rgba(239, 68, 68, 0.45); }
        .heat-loss-3 { background: rgba(239, 68, 68, 0.70); }
        .heat-loss-4 { background: rgba(220, 38, 38, 0.90); }
      `}</style>
    </PageShell>
  );
}
