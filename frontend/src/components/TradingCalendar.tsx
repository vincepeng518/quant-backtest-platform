'use client';

import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { Card } from '@/components/ui/Card';

export interface TradeItem {
  realizedProfit?: number;
  pnlRatio?: number;
  closeTime?: number | string;
  ts?: number;
  openTs?: number;
  status?: string;
  symbol?: string;
  side?: string;
  [key: string]: any;
}

interface TradingCalendarProps {
  records: TradeItem[];
  currencySymbol?: string;
}

/**
 * BY_MONTH_BASE — 按月拆分的交易 JSON 檔(儲存於 GitHub)。
 * 切換月份時動態載入對應月份檔,並在前端快取已載入月份。
 */
const GITHUB_RAW_BASE = 'https://raw.githubusercontent.com/vincepeng518/quant-backtest-platform/master';
const byMonthUrl = (ym: string) => `${GITHUB_RAW_BASE}/trades/by-month/${ym}.json`;

// 模組級快取:跨組件/跨切換累積已載入月份,避免重複 fetch
const _monthCache = new Map<string, TradeItem[]>();

async function fetchMonth(ym: string): Promise<TradeItem[]> {
  const cached = _monthCache.get(ym);
  if (cached) return cached;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch(byMonthUrl(ym), { signal: controller.signal, cache: 'force-cache' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const recs = (data?.records ?? []) as TradeItem[];
    _monthCache.set(ym, recs);
    return recs;
  } finally {
    clearTimeout(timer);
  }
}

// 從 timestamp 取月份 key YYYY-MM
function tsMonth(ts?: number | string): string | null {
  const t = typeof ts === 'number' ? ts : Number(ts);
  if (!t || Number.isNaN(t)) return null;
  const d = new Date(t);
  if (Number.isNaN(d.getTime())) return null;
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export const TradingCalendar: React.FC<TradingCalendarProps> = ({
  records,
  currencySymbol = '$',
}) => {
  const [currentDate, setCurrentDate] = useState(() => new Date());
  const [mode, setMode] = useState<'pnl' | 'events'>('pnl');

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();
  const monthKey = `${year}-${String(month + 1).padStart(2, '0')}`;

  const [monthLoading, setMonthLoading] = useState(false);
  const [monthError, setMonthError] = useState<string | null>(null);
  const [remoteRecords, setRemoteRecords] = useState<TradeItem[] | null>(null);
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const [metricLog, setMetricLog] = useState<{ key: string; ms: number; fromCache: boolean; size?: number }[]>([]);

  // ── 目前月是否「已含在 props records」─ props records 是後端全量,時間範圍可能涵蓋當前月
  // 若 props records 明確有該月資料,優先沿用(避免初次就打 GitHub),但為了「只有當月」需求,
  // 我們只在此 props 涵蓋月份時用它,否則動態載入。
  const byMonthFromProps = useMemo(() => {
    const map = new Map<string, TradeItem[]>();
    for (const r of records) {
      const m = tsMonth(r.closeTime ?? r.ts ?? r.openTs);
      if (m) {
        if (!map.has(m)) map.set(m, []);
        map.get(m)!.push(r);
      }
    }
    return map;
  }, [records]);

  // 切換月份 → 決定有效 records(優先 props 內同月資料,否則載入 GitHub 月份檔)
  const effectiveRecords = useMemo(() => {
    if (loadedKey === monthKey && remoteRecords) return remoteRecords;
    const fromProps = byMonthFromProps.get(monthKey);
    return fromProps ?? [];
  }, [monthKey, loadedKey, remoteRecords, byMonthFromProps]);

  const loadMonth = useCallback(
    async (ym: string) => {
      // 若 props 已涵蓋該月,不 fetch
      if (byMonthFromProps.has(ym) && byMonthFromProps.get(ym)!.length > 0) {
        setLoadedKey(ym);
        setRemoteRecords(byMonthFromProps.get(ym)!);
        setMonthError(null);
        setMonthLoading(false);
        return;
      }
      // 若已載入同月(remote),跳過
      if (loadedKey === ym && remoteRecords) { setMonthLoading(false); return; }
      const t0 = performance.now();
      setMonthLoading(true);
      setMonthError(null);
      // 先估大小(cache 判斷)
      const cacheHit = _monthCache.has(ym);
      try {
        const recs = await fetchMonth(ym);
        setRemoteRecords(recs);
        setLoadedKey(ym);
        const dt = performance.now() - t0;
        setMetricLog((prev) => [...prev.slice(-19), { key: ym, ms: dt, fromCache: cacheHit }]);
      } catch (e: any) {
        setMonthError(e?.message ?? '載入失敗');
        // 解析失敗 → 保留錯誤,UI 顯示,不崩潰
      } finally {
        setMonthLoading(false);
      }
    },
    [byMonthFromProps, loadedKey, remoteRecords]
  );

  // 月份或 props 改變時觸發載入僅當該月不在 props / 未載入
  useEffect(() => {
    const inProps = byMonthFromProps.get(monthKey);
    // 若該月 props 有資料用 props;否則需要載入(除非正在載入同月)
    if (inProps && inProps.length > 0) {
      setLoadedKey(monthKey);
      setRemoteRecords(inProps);
      setMonthError(null);
      return;
    }
    if (loadedKey === monthKey && remoteRecords) return;
    loadMonth(monthKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [monthKey, byMonthFromProps]); // 只對 monthKey / byMonthFromProps 改變觸發

  const handlePrevMonth = () => setCurrentDate(new Date(year, month - 1, 1));
  const handleNextMonth = () => setCurrentDate(new Date(year, month + 1, 1));
  const handleToday = () => setCurrentDate(new Date());

  // ── Daily Group By(原邏輯保留,輸入改為 effectiveRecords)──
  const dailySummary = useMemo(() => {
    const summary: Record<
      string,
      { totalPnl: number; totalCount: number; winCount: number; trades: TradeItem[] }
    > = {};

    effectiveRecords.forEach((r) => {
      const closeTs = r.closeTime || r.ts || r.openTs;
      if (!closeTs) return;
      const dateObj = new Date(closeTs);
      if (isNaN(dateObj.getTime())) return;

      const yyyy = dateObj.getFullYear();
      const mm = String(dateObj.getMonth() + 1).padStart(2, '0');
      const dd = String(dateObj.getDate()).padStart(2, '0');
      const dateKey = `${yyyy}-${mm}-${dd}`;

      if (!summary[dateKey]) {
        summary[dateKey] = { totalPnl: 0, totalCount: 0, winCount: 0, trades: [] };
      }

      const pnl = Number(r.realizedProfit ?? 0);
      summary[dateKey].totalPnl += pnl;
      summary[dateKey].totalCount += 1;
      if (pnl > 0) {
        summary[dateKey].winCount += 1;
      }
      summary[dateKey].trades.push(r);
    });

    return summary;
  }, [effectiveRecords]);

  // ── 月曆網格(原邏輯)──
  const calendarCells = useMemo(() => {
    const firstDayOfWeek = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const cells: Array<{ dayNum: number | null; dateKey: string | null; isToday: boolean }> = [];
    for (let i = 0; i < firstDayOfWeek; i++) {
      cells.push({ dayNum: null, dateKey: null, isToday: false });
    }
    const now = new Date();
    const isCurrentMonthYear = now.getFullYear() === year && now.getMonth() === month;
    for (let d = 1; d <= daysInMonth; d++) {
      const mm = String(month + 1).padStart(2, '0');
      const dd = String(d).padStart(2, '0');
      const dateKey = `${year}-${mm}-${dd}`;
      const isToday = isCurrentMonthYear && now.getDate() === d;
      cells.push({ dayNum: d, dateKey, isToday });
    }
    return cells;
  }, [year, month]);

  const monthLabel = `${year}年${month + 1}月`;
  const weekDays = ['日', '一', '二', '三', '四', '五', '六'];

  const colorVars = {
    '--tc-page-bg': '#0B0E11', '--tc-card-bg': '#12151A', '--tc-cell-default-bg': '#181B20',
    '--tc-cell-default-border': '#22262E', '--tc-profit-bg': '#12251E', '--tc-profit-text': '#36D399',
    '--tc-profit-border': '#1E4D3B', '--tc-loss-bg': '#2A181C', '--tc-loss-text': '#F87171',
    '--tc-loss-border': '#52222B', '--tc-main-text': '#EAECF0', '--tc-secondary-text': '#858D9D',
    '--tc-light-page-bg': '#F7F7F5', '--tc-light-card-bg': '#FFFFFF', '--tc-light-cell-default-bg': '#F2F1ED',
    '--tc-light-cell-default-border': '#E5E4DF', '--tc-light-profit-bg': '#E6F4EA', '--tc-light-profit-text': '#137333',
    '--tc-light-profit-border': '#CEEAD6', '--tc-light-loss-bg': '#FCE8E6', '--tc-light-loss-text': '#C5221F',
    '--tc-light-loss-border': '#FAD2CF', '--tc-light-main-text': '#1A1A1A', '--tc-light-secondary-text': '#666666',
  };

  return (
    <Card className="p-5 space-y-4 relative overflow-hidden">
      <style jsx global>{`
        .trading-calendar-root { --tc-page-bg: #0B0E11; --tc-card-bg: #12151A; --tc-cell-default-bg: #181B20; --tc-cell-default-border: #22262E; --tc-profit-bg: #12251E; --tc-profit-text: #36D399; --tc-profit-border: #1E4D3B; --tc-loss-bg: #2A181C; --tc-loss-text: #F87171; --tc-loss-border: #52222B; --tc-main-text: #EAECF0; --tc-secondary-text: #858D9D; }
        :root.dark .trading-calendar-root, .dark .trading-calendar-root { --tc-page-bg: #0B0E11; --tc-card-bg: #12151A; --tc-cell-default-bg: #181B20; --tc-cell-default-border: #22262E; --tc-profit-bg: #12251E; --tc-profit-text: #36D399; --tc-profit-border: #1E4D3B; --tc-loss-bg: #2A181C; --tc-loss-text: #F87171; --tc-loss-border: #52222B; --tc-main-text: #EAECF0; --tc-secondary-text: #858D9D; }
        :root:not(.dark) .trading-calendar-root, .light .trading-calendar-root { --tc-page-bg: #F7F7F5; --tc-card-bg: #FFFFFF; --tc-cell-default-bg: #F2F1ED; --tc-cell-default-border: #E5E4DF; --tc-profit-bg: #E6F4EA; --tc-profit-text: #137333; --tc-profit-border: #CEEAD6; --tc-loss-bg: #FCE8E6; --tc-loss-text: #C5221F; --tc-loss-border: #FAD2CF; --tc-main-text: #1A1A1A; --tc-secondary-text: #666666; }
      `}</style>

      <div className="trading-calendar-root">
        {/* Header 原結構保留 */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-4" style={{ borderColor: 'var(--tc-cell-default-border)', color: 'var(--tc-main-text)' }}>
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold font-sans" style={{ color: 'var(--tc-main-text)' }}>Trading Calendar</h2>
            <div className="flex items-center p-1 rounded-lg text-xs font-mono" style={{ backgroundColor: 'var(--tc-cell-default-bg)', borderColor: 'var(--tc-cell-default-border)', borderWidth: 1 }}>
              <button onClick={() => setMode('pnl')} className="px-3 py-1 rounded-md transition-colors font-medium" style={{ backgroundColor: mode === 'pnl' ? 'var(--tc-profit-text)' : 'transparent', color: mode === 'pnl' ? '#000000' : 'var(--tc-secondary-text)' }}>PNL</button>
              <button onClick={() => setMode('events')} className="px-3 py-1 rounded-md transition-colors font-medium" style={{ backgroundColor: mode === 'events' ? 'var(--tc-profit-text)' : 'transparent', color: mode === 'events' ? '#000000' : 'var(--tc-secondary-text)' }}>Events</button>
            </div>
          </div>
          <div className="flex items-center gap-2 font-mono text-sm">
            <span className="font-bold px-2" style={{ color: 'var(--tc-main-text)' }}>{monthLabel}</span>
            <div className="flex items-center gap-1">
              <button onClick={handlePrevMonth} className="px-2.5 py-1 rounded transition-colors" style={{ backgroundColor: 'var(--tc-cell-default-bg)', border: '1px solid var(--tc-cell-default-border)', color: 'var(--tc-secondary-text)' }}>&lt;</button>
              <button onClick={handleToday} className="px-2 py-1 rounded transition-colors text-xs" style={{ backgroundColor: 'var(--tc-cell-default-bg)', border: '1px solid var(--tc-cell-default-border)', color: 'var(--tc-secondary-text)' }}>Today</button>
              <button onClick={handleNextMonth} className="px-2.5 py-1 rounded transition-colors" style={{ backgroundColor: 'var(--tc-cell-default-bg)', border: '1px solid var(--tc-cell-default-border)', color: 'var(--tc-secondary-text)' }}>&gt;</button>
            </div>
          </div>
        </div>

        {/* 動態載入狀態列 */}
        {(monthLoading || monthError) && (
          <div className="text-xs font-mono px-1" style={{ color: monthError ? 'var(--tc-loss-text)' : 'var(--tc-secondary-text)' }}>
            {monthLoading ? `載入 ${monthKey} 資料…` : monthError ? `⚠ ${monthKey} 載入失敗: ${monthError} (請檢查 GitHub 月份檔,或重試)` : null}
          </div>
        )}

        {/* Grid 原結構保留,cell 依 effectiveRecords 的 dailySummary */}
        <div className="grid grid-cols-7 gap-1.5 font-mono" style={{ backgroundColor: 'var(--tc-card-bg)' }}>
          {weekDays.map((wd) => (
            <div key={wd} className="text-center py-1 text-xs font-semibold" style={{ color: 'var(--tc-secondary-text)', borderBottom: '1px solid var(--tc-cell-default-border)' }}>{wd}</div>
          ))}
          {calendarCells.map((cell, idx) => {
            if (!cell.dayNum || !cell.dateKey) {
              return <div key={`empty-${idx}`} className="min-h-[76px] rounded-lg" style={{ backgroundColor: 'var(--tc-cell-default-bg)', opacity: 0.3 }} />;
            }
            const dayData = dailySummary[cell.dateKey];
            const hasTrade = dayData && dayData.totalCount > 0;
            const pnl = dayData?.totalPnl ?? 0;
            const winRate = hasTrade ? Math.round((dayData.winCount / dayData.totalCount) * 100) : 0;

            let cellBg: string, cellTextColor: string, cellBorder: string;
            if (hasTrade) {
              if (pnl > 0) { cellBg = 'var(--tc-profit-bg)'; cellTextColor = 'var(--tc-profit-text)'; cellBorder = 'var(--tc-profit-border)'; }
              else if (pnl < 0) { cellBg = 'var(--tc-loss-bg)'; cellTextColor = 'var(--tc-loss-text)'; cellBorder = 'var(--tc-loss-border)'; }
              else { cellBg = 'var(--tc-cell-default-bg)'; cellTextColor = 'var(--tc-main-text)'; cellBorder = 'var(--tc-cell-default-border)'; }
            } else {
              cellBg = 'var(--tc-cell-default-bg)'; cellTextColor = 'var(--tc-main-text)'; cellBorder = 'var(--tc-cell-default-border)';
            }

            const fmtPnl = (val: number) => {
              const absVal = Math.abs(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
              return val >= 0 ? `${currencySymbol}${absVal}` : `-${currencySymbol}${absVal}`;
            };

            return (
              <div key={cell.dateKey} className="flex flex-col items-center justify-center min-h-[68px] rounded-lg border transition-all text-center" style={{ backgroundColor: cellBg, borderColor: cell.isToday ? 'var(--tc-profit-text)' : cellBorder, borderWidth: 1, outline: cell.isToday ? '2px solid var(--tc-profit-text)' : 'none', outlineOffset: '-2px', padding: '4px 2px' }}>
                <div className="text-sm font-bold leading-tight" style={{ color: cell.isToday ? 'var(--tc-profit-text)' : 'var(--tc-secondary-text)' }}>{cell.dayNum}</div>
                {hasTrade ? (
                  mode === 'pnl' ? (
                    <div className="mt-0.5 text-center leading-tight" style={{ color: cellTextColor }}>
                      <div className="text-sm font-bold">{fmtPnl(pnl)}</div>
                      <div className="text-[10px]" style={{ opacity: 0.75 }}>{winRate}%</div>
                    </div>
                  ) : (
                    <div className="mt-0.5 text-center leading-tight" style={{ color: cellTextColor }}>
                      <div className="text-sm font-bold">{fmtPnl(pnl)}</div>
                      <div className="text-[10px]" style={{ opacity: 0.75 }}>{dayData.winCount}W|{dayData.totalCount - dayData.winCount}L</div>
                    </div>
                  )
                ) : null}
              </div>
            );
          })}
        </div>

        {/* 載入測速儀表(調試用,讓開發者可看到每個月載入耗時與是否 cache) */}
        {metricLog.length > 0 && false}
      </div>
    </Card>
  );
};
