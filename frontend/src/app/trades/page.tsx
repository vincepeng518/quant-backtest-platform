'use client';

import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import Link from 'next/link';
import { PageShell } from '@/components/layout/PageShell';
import { Card } from '@/components/ui/Card';
import { TradingCalendar } from '@/components/TradingCalendar';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { api, getTradesSummary, getMonthTrades, getLatestTrades } from '@/lib/api';
import { fmtProfitFactor } from '@/lib/format';

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
  entry_fee?: number;
  exit_fee?: number;
  fundingFee?: number;
  status?: string;
  ts?: number;
  closeTime?: number;
  holdDuration?: number;
  _snapshot?: string;
  bet_usd?: number;
  ask_price?: number;
  market_id?: string;
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
  const [records, setRecords] = useState<TradeRec[]>([]);   // 當月交易(rB: decouple 後當月明細)
  const [summary, setSummary] = useState<any>(null);          // summary.json 全量統計 SSOT
  const [viewMonth, setViewMonth] = useState<string>(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<Range>('all');
  const [currentPage, setCurrentPage] = useState<number>(1);
  const pageSize = 25;
  const [selectedTrade, setSelectedTrade] = useState<TradeRec | null>(null);
  const [heartbeat, setHeartbeat] = useState<{ alive: boolean; updated_at: string | null } | null>(null);

  useEffect(() => {
    if (source !== 'predict') return;
    api.getPredictHeartbeat()
      .then((d: any) => setHeartbeat({ alive: d.alive, updated_at: d.updated_at }))
      .catch(() => setHeartbeat(null)); // Hide status if endpoint doesn't exist
  }, [source]);

  // ══ 跨月表格序列 + 分頁 ══
  // 首載: latest_trades.json(跨月最新50) → summary。往下載更多: 依 summary.months[] 依序向後補 by-month。
  // 表格 `records` = 跨月降冪序列(ts), 跨月去重; 日曆仍獨立依月份載入。
  const [monthIndex, setMonthIndex] = useState(1);   // 下一個待載月份在 summary.months 的 index(latest 已涵蓋前幾個月)
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);

  // 指紋去重(跨月 append 防重複)
  const fp = (r: any) => `${r.ts ?? ''}|${r.symbol ?? ''}|${r.side ?? ''}|${r.realizedProfit ?? ''}`;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSelectedTrade(null);
    setCurrentPage(1);
    if (source === 'bingx') {
      Promise.all([getTradesSummary(), getLatestTrades()])
        .then(([s, latest]) => {
          if (cancelled) return;
          if (s) setSummary(s);
          setRecords((latest ?? []).sort((a: any, b: any) => sortKey(b) - sortKey(a)));
          // monthIndex = latest 已涵蓋 summary.months 前 N 個月(無需重載)
          const latestMonths = (latest as any)?.months?.length;
          const covered = Array.isArray(latestMonths) ? (latest as any).months.length : (latestMonths ?? 2);
          setMonthIndex(covered); // 下一個待載 = months[covered](更早一月)
          setHasMore((s?.months?.length ?? 0) > covered);
        })
        .catch((e) => { if (!cancelled) setError(e?.message ?? 'failed to load trades'); })
        .finally(() => { if (!cancelled) setLoading(false); });
    } else {
      const fetcher = source === 'arb' ? api.getArbTrades() : api.getPredictTrades();
      fetcher
        .then((d: any) => { if (cancelled) return; setRecords((d.records ?? []).sort((a: any, b: any) => sortKey(b) - sortKey(a))); })
        .catch((e) => { if (!cancelled) setError(e?.message ?? 'failed to load trades'); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }
    return () => { cancelled = true; };
  }, [source]);

  // 載入下一個更早月份(跨月補載,去重 append)
  const loadMoreMonth = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    if (!summary?.months?.length) { setHasMore(false); return; }
    const idx = monthIndexRef.current;
    if (idx >= summary.months.length) { setHasMore(false); return; }
    const ym = summary.months[idx];
    setLoadingMore(true);
    try {
      const more = await getMonthTrades(ym);
      setRecords((prev) => {
        const seen = new Set(prev.map(fp));
        const added = more.filter((r: any) => !seen.has(fp(r)));
        const merged = [...prev, ...added].sort((a: any, b: any) => sortKey(b) - sortKey(a));
        return merged;
      });
      setMonthIndex((i) => i + 1);
    } catch (e: any) {
      setError(e?.message ?? '載入更早月份失敗');
    } finally {
      setLoadingMore(false);
    }
  }, [loadingMore, hasMore, summary]);

  // 滾動到底自動載入更早月份(滾動分頁)
  useEffect(() => {
    const onScroll = () => {
      if (!hasMore || loadingMore) return;
      const nearBottom = window.innerHeight + window.scrollY >= document.body.offsetHeight - 300;
      if (nearBottom) loadMoreMonth();
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [hasMore, loadingMore, loadMoreMonth]);

  const monthIndexRef = useRef(1);
  monthIndexRef.current = monthIndex;

  // summary.metrics 簡化取用
  const metrics = summary?.metrics ?? null;
  // 手續費 = summary 全期費用
  const feesTotal = summary?.totals?.fees_total ?? null;

  // 當月統計卡資料(優先 summary.monthly_agg[該月],無則用全期 totals)
  const monthStat = summary?.monthly_agg?.[viewMonth] ?? null;

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

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageRecords = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, currentPage, pageSize]);

  // ══ 統計卡資料(單一來源 = summary.json 全量 SSOT, 與舊全量 /api/trades 一致)══
  const stats = useMemo(() => {
    const t = summary?.totals;
    if (!t) {
      return { totalPnl: 0, totalPos: 0, wins: 0, losses: 0, scr: 0, winRate: 0, avgPnl: 0,
               longPnl: 0, shortPnl: 0, gainsAmt: 0, lossesAmt: 0, maxWinStreak: 0, maxLossStreak: 0 };
    }
    return {
      totalPnl: t.pnl ?? 0, totalPos: t.position_value ?? 0,
      wins: t.wins ?? 0, losses: t.losses ?? 0, scr: t.scratch ?? 0,
      winRate: t.win_rate ?? 0, avgPnl: t.avg_pnl ?? 0,
      longPnl: t.long_pnl ?? 0, shortPnl: t.short_pnl ?? 0,
      gainsAmt: t.gains_amt ?? 0, lossesAmt: t.losses_amt ?? 0,
      maxWinStreak: t.max_win_streak ?? 0, maxLossStreak: t.max_loss_streak ?? 0,
    };
  }, [summary]);

  // 當月(30d)統計卡: 優先 monthly_agg[viewMonth], 無則用全期 totals
  const monthStatCard = useMemo(() => {
    const m = summary?.monthly_agg?.[viewMonth];
    if (!m) return null;
    const wins = m.wins ?? 0, losses = m.losses ?? 0;
    return { win_rate: losses + wins > 0 ? (wins / (losses + wins)) * 100 : 0, wins, losses, pnl: m.pnl ?? 0 };
  }, [summary, viewMonth]);

  // PnL Calendar Heatmap — 用 summary.heatmap_12w(全量,與舊版一致)
  const heatmap = useMemo<{ key: string; pnl: number; dow: number }[]>(() => {
    if (summary?.heatmap_12w) return summary.heatmap_12w;
    return [];
  }, [summary]);

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
            onClick={() => { setSource(s.key); setCurrentPage(1); }}
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
            onClick={() => { setRange(t.key); setCurrentPage(1); }}
            className={`px-3 py-1.5 rounded-md text-sm font-mono transition-colors ${
              range === t.key ? 'bg-accent text-background font-medium' : 'bg-surface text-textSecondary hover:text-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 統計卡 (journalit 風格) — 全期統計來自 summary.json, 有統計即顯示 */}
      {summary && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">P/L (全期)</p>
              <p className={`text-xl font-mono font-semibold ${stats.totalPnl >= 0 ? 'text-accent' : 'text-danger'}`}>
                {stats.totalPnl >= 0 ? '+' : ''}{fmt(stats.totalPnl)} USDT
              </p>
              <p className="text-xs text-textSecondary font-mono mt-0.5">
                ≈ {stats.totalPnl >= 0 ? '+' : ''}{fmt(stats.totalPnl * 32.5)} TWD
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
                {stats.avgPnl >= 0 ? '+' : ''}{fmt(stats.avgPnl)} USDT
              </p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">總倉位大小</p>
              <p className="text-xl font-mono font-semibold text-text">{fmt(stats.totalPos)} USDT</p>
            </Card>
          </div>

          {/* 30d 統計 (保留勝率) — 來源 monthStatCard=summary.monthly_agg[該月] */}
          {monthStatCard && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <Card className="p-4">
                <p className="text-xs text-textSecondary font-mono mb-1">勝率 ({viewMonth})</p>
                <p className="text-xl font-mono font-semibold text-text">{fmt(monthStatCard.win_rate ?? 0, 1)}%</p>
                <p className="text-xs text-textSecondary font-mono">{monthStatCard.wins}W / {monthStatCard.losses}L</p>
              </Card>
              <Card className="p-4">
                <p className="text-xs text-textSecondary font-mono mb-1">盈利 / 虧損金額 (全期)</p>
                <p className="text-sm font-mono">
                  <span className="text-accent">+{fmt(stats.gainsAmt ?? 0)} USDT</span>
                  {' / '}
                  <span className="text-danger">{fmt(stats.lossesAmt ?? 0)} USDT</span>
                </p>
              </Card>
            </div>
          )}

          {/* 手續費 (另計, 不併入 P/L) */}
          {feesTotal != null && feesTotal !== 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <Card className="p-4">
                <p className="text-xs text-textSecondary font-mono mb-1">手續費 (Fees)</p>
                <p className="text-xl font-mono font-semibold text-danger">-{fmt(feesTotal)} USDT</p>
              </Card>
            </div>
          )}

          {/* 多空 + 連續 (第二排) */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">多頭 P/L</p>
              <p className={`text-lg font-mono font-semibold ${stats.longPnl >= 0 ? 'text-accent' : 'text-danger'}`}>
                {stats.longPnl >= 0 ? '+' : ''}{fmt(stats.longPnl)} USDT
              </p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">空頭 P/L</p>
              <p className={`text-lg font-mono font-semibold ${stats.shortPnl >= 0 ? 'text-accent' : 'text-danger'}`}>
                {stats.shortPnl >= 0 ? '+' : ''}{fmt(stats.shortPnl)} USDT
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

          {/* 專業績效指標 (保留 Sharpe + Profit Factor) */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">Sharpe</p>
              <p className="text-xl font-mono font-semibold text-text">{metrics?.sharpe ?? '—'}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-textSecondary font-mono mb-1">Profit Factor</p>
              <p className="text-xl font-mono font-semibold text-accent">{fmtProfitFactor(metrics?.profit_factor)}</p>
            </Card>
          </div>
        </>
      )}

      {/* 交易日曆組件 — 切月同步載入當月表格 */}
      <TradingCalendar records={records} onMonthChange={setViewMonth} />

      {/* 交易表格 — 當月明細 (rB: 已解耦全量, 顯示 viewMonth 當月) */}
      <Card className="min-h-[300px]">
        <div className="flex items-center justify-between px-4 pt-3 pb-1 border-b border-border/10">
          <span className="text-sm font-semibold text-text">跨月交易 (最新 {filtered.length} 筆{loading || !hasMore ? '' : ` / ${monthIndex + 1} 個月`})</span>
          <span className="text-xs font-mono text-textSecondary">
            {loading ? '載入中…' : loadingMore ? `載入 ${summary?.months?.[monthIndex] ?? ''}…` : ((hasMore && summary?.months?.length) ? summary.months[monthIndex] ? '' : '' : '全部歷史已載入')}
          </span>
        </div>
        {loading ? (
          <div className="flex justify-center py-12"><Spinner size="lg" /></div>
        ) : error ? (
          <div className="p-6">
            <p className="text-sm font-mono text-danger">載入失敗 — 請稍後重試</p>
            <p className="text-xs font-mono text-textSecondary mt-1 opacity-70 truncate max-w-full">{error}</p>
          </div>
        ) : records.length === 0 ? (
          <EmptyState title="暫無交易記錄" description={source === 'arb' ? "Arb bot 尚未成交 (DRY_RUN 或無套利信號)。" : source === 'predict' ? "Predict.fun 15m BTC/ETH 預測市場尚無持倉。" : "尚無交易,等待 bot 抓取。"} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-base font-mono">
              <thead>
                <tr className="text-textSecondary text-sm border-b border-border/20">
                  <th className="text-left px-4 py-3">Symbol / Side</th>
                  <th className="text-right px-4 py-3">{source === 'predict' ? 'Side' : '名義 / 槓桿'}</th>
                  <th className="text-right px-4 py-3">盈虧 (PnL) / 盈虧率</th>
                  <th className="text-right px-4 py-3">平倉時間</th>
                  <th className="text-center px-4 py-3">操作</th>
                </tr>
              </thead>
              <tbody>
                {pageRecords.map((r, i) => {
                  const p = pnlOf(r);
                  const closeTs = r.closeTime || r.ts || sortKey(r);
                  const notionalVal = r.notional ? fmt(r.notional) : (r.positionValue ? fmt(r.positionValue) : '—');
                  const levStr = r.leverage != null ? `(${r.leverage}x)` : '';
                  const sideStr = r.side ? `(${r.side})` : '';

                  const marginVal = Number(r.margin) || (r.notional && r.leverage ? Number(r.notional) / Number(r.leverage) : (r.positionValue && r.leverage ? Number(r.positionValue) / Number(r.leverage) : 0));
                  const sideLabel = source === 'predict' ? (r.side || '—') : notionalVal;
                  const sideExtra = source === 'predict' ? '' : levStr;
                  const pnlRate = r.pnlRatio != null && r.pnlRatio !== 0
                    ? Number(r.pnlRatio)
                    : (marginVal > 0 ? (p / marginVal) * 100 : 0);
                  const pnlRateStr = pnlRate !== 0 ? ` (${pnlRate >= 0 ? '+' : ''}${pnlRate.toFixed(2)}%)` : '';

                  return (
                    <tr
                      key={i}
                      onClick={() => setSelectedTrade(r)}
                      className="border-b border-border/10 hover:bg-surface/60 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3.5 font-medium text-text">
                        <span>{simplifySymbol(r.symbol)}</span>
                        {source !== 'predict' && <>{' '}<span className="text-sm text-textSecondary font-normal">{sideStr}</span></>}
                      </td>
                      <td className="px-4 py-3.5 text-right text-text font-mono">
                        <span>{sideLabel}</span>{' '}
                        <span className="text-sm text-textSecondary">{sideExtra}</span>
                      </td>
                      <td className={`px-4 py-3.5 text-right font-medium ${p >= 0 ? 'text-accent' : 'text-danger'}`}>
                        <span>{p >= 0 ? '+' : ''}{fmt(p)}</span>
                        <span className="text-sm ml-1 font-normal opacity-90">{pnlRateStr}</span>
                      </td>
                      <td className="px-4 py-3.5 text-right text-textSecondary text-sm">
                        {closeTs ? new Date(closeTs).toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'}
                      </td>
                      <td className="px-4 py-3.5 text-center">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedTrade(r);
                          }}
                          className="px-2.5 py-1 text-xs rounded bg-surface hover:bg-surface/80 border border-border/30 text-textSecondary hover:text-text transition-colors"
                        >
                          詳情
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {/* Pagination controls */}
        {!loading && !error && filtered.length > 0 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-border/20 text-xs font-mono">
            <span className="text-textSecondary">
              顯示 {(currentPage - 1) * pageSize + 1} - {Math.min(currentPage * pageSize, filtered.length)} / 共 {filtered.length} 筆
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                className="px-2.5 py-1 rounded bg-surface hover:bg-surface/80 border border-border/30 text-text disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                title="上一頁"
              >
                &lt;
              </button>
              <span className="text-text font-medium px-1">
                {currentPage} / {totalPages}
              </span>
              <button
                disabled={currentPage >= totalPages}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                className="px-2.5 py-1 rounded bg-surface hover:bg-surface/80 border border-border/30 text-text disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                title="下一頁"
              >
                &gt;
              </button>
            </div>
          </div>
        )}
        {/* 載入更多跨月歷史(滾動到底或點按鈕) */}
        {(hasMore && records.length > 0 && source === 'bingx') && (
          <div className="flex items-center justify-center px-4 py-3 border-t border-border/10">
            <button
              onClick={loadMoreMonth}
              disabled={loadingMore}
              className="px-4 py-2 rounded-md bg-surface hover:bg-surface/80 border border-border/30 text-sm font-mono text-textSecondary hover:text-text disabled:opacity-40 disabled:cursor-wait transition-colors"
            >
              {loadingMore ? `載入 ${summary?.months?.[monthIndex] ?? ''}…` : `載入更早月份 (${summary?.months?.[monthIndex] ?? '…'})`}
            </button>
          </div>
        )}
      </Card>

      {/* 交易詳情 Modal 彈窗 */}
      {selectedTrade && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
          onClick={() => setSelectedTrade(null)}
        >
          <div
            className="w-full max-w-md bg-surface border border-border/40 rounded-xl p-6 shadow-2xl font-mono"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-4 border-b border-border/20">
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold text-text">{simplifySymbol(selectedTrade.symbol)}</span>
                <span className={`text-xs px-2 py-0.5 rounded font-medium ${selectedTrade.side?.includes('LONG') ? 'bg-accent/20 text-accent' : 'bg-danger/20 text-danger'}`}>
                  {selectedTrade.side}
                </span>
              </div>
              <button
                onClick={() => setSelectedTrade(null)}
                className="text-textSecondary hover:text-text text-xl leading-none px-2 py-1"
              >
                ✕
              </button>
            </div>

            <div className="py-4 space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-textSecondary">數量 (Qty)</span>
                <span className="text-text">{fmtQty(selectedTrade.qty ?? selectedTrade.positionAmt)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">開倉價格</span>
                <span className="text-text">{fmtPrice(selectedTrade.avgPrice)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">平倉價格</span>
                <span className="text-text">{fmtPrice(selectedTrade.exitPrice)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">{source === 'predict' ? 'Side' : '槓桿倍數'}</span>
                <span className="text-text">{source === 'predict' ? (selectedTrade.side || '—') : (selectedTrade.leverage != null ? `${selectedTrade.leverage}x` : '—')}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">{source === 'predict' ? 'Bet (USD)' : '名義價值'}</span>
                <span className="text-text">{source === 'predict' ? (selectedTrade.bet_usd != null ? fmt(selectedTrade.bet_usd) : '—') : (selectedTrade.notional ? fmt(selectedTrade.notional) : (selectedTrade.positionValue ? fmt(selectedTrade.positionValue) : '—'))}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">盈虧 (PnL)</span>
                <span className={`font-medium ${pnlOf(selectedTrade) >= 0 ? 'text-accent' : 'text-danger'}`}>
                  {pnlOf(selectedTrade) >= 0 ? '+' : ''}{fmt(pnlOf(selectedTrade))}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">手續費</span>
                <span className="text-danger">
                  {(selectedTrade as any).fee != null && Number((selectedTrade as any).fee) !== 0
                    ? `-${fmt(Math.abs(Number((selectedTrade as any).fee)), 4)}`
                    : ((selectedTrade as any).entry_fee || (selectedTrade as any).exit_fee
                        ? `-${fmt(Math.abs(Number((selectedTrade as any).entry_fee ?? 0) + Number((selectedTrade as any).exit_fee ?? 0)), 4)}`
                        : '—')}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">開倉時間</span>
                <span className="text-text">
                  {sortKey(selectedTrade)
                    ? new Date(sortKey(selectedTrade)).toLocaleString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
                    : '—'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">平倉時間</span>
                <span className="text-text">
                  {selectedTrade.closeTime
                    ? new Date(selectedTrade.closeTime).toLocaleString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
                    : '—'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">持倉時間</span>
                <span className="text-text">{fmtDuration(selectedTrade.holdDuration)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">狀態</span>
                <span className="text-text">{selectedTrade.status}</span>
              </div>
            </div>

            <div className="pt-3 border-t border-border/20 text-right">
              <button
                onClick={() => setSelectedTrade(null)}
                className="px-4 py-1.5 text-xs rounded bg-surface hover:bg-surface/80 border border-border/30 text-text font-medium transition-colors"
              >
                關閉
              </button>
            </div>
          </div>
        </div>
      )}

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
