'use client';

import React, { useState, useMemo } from 'react';
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

export const TradingCalendar: React.FC<TradingCalendarProps> = ({
  records,
  currencySymbol = '$',
}) => {
  const [currentDate, setCurrentDate] = useState(() => new Date());
  const [mode, setMode] = useState<'pnl' | 'events'>('pnl');

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  // ── Daily Group By ──
  const dailySummary = useMemo(() => {
    const summary: Record<
      string,
      { totalPnl: number; totalCount: number; winCount: number; trades: TradeItem[] }
    > = {};

    records.forEach((r) => {
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
  }, [records]);

  const handlePrevMonth = () => setCurrentDate(new Date(year, month - 1, 1));
  const handleNextMonth = () => setCurrentDate(new Date(year, month + 1, 1));
  const handleToday = () => setCurrentDate(new Date());

  // ── 月曆網格 ──
  const calendarCells = useMemo(() => {
    const firstDayOfWeek = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    const cells: Array<{
      dayNum: number | null;
      dateKey: string | null;
      isToday: boolean;
    }> = [];

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
  const weekDays = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];

  // ── CSS Variables 注入：精準配色 ──
  // 暗色（Lucid Trading）＆ 亮色（Cursor 官網）
  const colorVars = {
    '--tc-page-bg': '#0B0E11',
    '--tc-card-bg': '#12151A',
    '--tc-cell-default-bg': '#181B20',
    '--tc-cell-default-border': '#22262E',
    '--tc-profit-bg': '#12251E',
    '--tc-profit-text': '#36D399',
    '--tc-profit-border': '#1E4D3B',
    '--tc-loss-bg': '#2A181C',
    '--tc-loss-text': '#F87171',
    '--tc-loss-border': '#52222B',
    '--tc-main-text': '#EAECF0',
    '--tc-secondary-text': '#858D9D',
    '--tc-light-page-bg': '#F7F7F5',
    '--tc-light-card-bg': '#FFFFFF',
    '--tc-light-cell-default-bg': '#F2F1ED',
    '--tc-light-cell-default-border': '#E5E4DF',
    '--tc-light-profit-bg': '#E6F4EA',
    '--tc-light-profit-text': '#137333',
    '--tc-light-profit-border': '#CEEAD6',
    '--tc-light-loss-bg': '#FCE8E6',
    '--tc-light-loss-text': '#C5221F',
    '--tc-light-loss-border': '#FAD2CF',
    '--tc-light-main-text': '#1A1A1A',
    '--tc-light-secondary-text': '#666666',
  };

  return (
    <Card className="p-5 space-y-4 relative overflow-hidden">
      {/* 全域 CSS 變數 + 淺/暗色切換樣式 */}
      <style jsx global>{`
        .trading-calendar-root {
          /* 暗色預設值 */
          --tc-page-bg: #0B0E11;
          --tc-card-bg: #12151A;
          --tc-cell-default-bg: #181B20;
          --tc-cell-default-border: #22262E;
          --tc-profit-bg: #12251E;
          --tc-profit-text: #36D399;
          --tc-profit-border: #1E4D3B;
          --tc-loss-bg: #2A181C;
          --tc-loss-text: #F87171;
          --tc-loss-border: #52222B;
          --tc-main-text: #EAECF0;
          --tc-secondary-text: #858D9D;
          --tc-cell-empty-bg: #101318;
          --tc-cell-empty-border: #191D24;
        }
        :root.dark .trading-calendar-root,
        .dark .trading-calendar-root {
          --tc-page-bg: #0B0E11;
          --tc-card-bg: #12151A;
          --tc-cell-default-bg: #181B20;
          --tc-cell-default-border: #22262E;
          --tc-profit-bg: #12251E;
          --tc-profit-text: #36D399;
          --tc-profit-border: #1E4D3B;
          --tc-loss-bg: #2A181C;
          --tc-loss-text: #F87171;
          --tc-loss-border: #52222B;
          --tc-main-text: #EAECF0;
          --tc-secondary-text: #858D9D;
          --tc-cell-empty-bg: #101318;
          --tc-cell-empty-border: #191D24;
        }
        :root:not(.dark) .trading-calendar-root,
        .light .trading-calendar-root {
          --tc-page-bg: #F7F7F5;
          --tc-card-bg: #FFFFFF;
          --tc-cell-default-bg: #F2F1ED;
          --tc-cell-default-border: #E5E4DF;
          --tc-profit-bg: #E6F4EA;
          --tc-profit-text: #137333;
          --tc-profit-border: #CEEAD6;
          --tc-loss-bg: #FCE8E6;
          --tc-loss-text: #C5221F;
          --tc-loss-border: #FAD2CF;
          --tc-main-text: #1A1A1A;
          --tc-secondary-text: #666666;
          --tc-cell-empty-bg: #FDFDFC;
          --tc-cell-empty-border: #F0EFEA;
        }
      `}</style>

      <div className="trading-calendar-root">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-4" style={{ borderColor: 'var(--tc-cell-default-border)', color: 'var(--tc-main-text)' }}>
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold font-sans" style={{ color: 'var(--tc-main-text)' }}>
              Trading Calendar
            </h2>
            <div
              className="flex items-center p-1 rounded-lg text-xs font-mono"
              style={{
                backgroundColor: 'var(--tc-cell-default-bg)',
                borderColor: 'var(--tc-cell-default-border)',
                borderWidth: 1,
              }}
            >
              <button
                onClick={() => setMode('pnl')}
                className="px-3 py-1 rounded-md transition-colors font-medium"
                style={{
                  backgroundColor: mode === 'pnl' ? 'var(--tc-profit-text)' : 'transparent',
                  color: mode === 'pnl' ? '#000000' : 'var(--tc-secondary-text)',
                }}
              >
                PNL
              </button>
              <button
                onClick={() => setMode('events')}
                className="px-3 py-1 rounded-md transition-colors font-medium"
                style={{
                  backgroundColor: mode === 'events' ? 'var(--tc-profit-text)' : 'transparent',
                  color: mode === 'events' ? '#000000' : 'var(--tc-secondary-text)',
                }}
              >
                Events
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2 font-mono text-sm">
            <span className="font-bold px-2" style={{ color: 'var(--tc-main-text)' }}>
              {monthLabel}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={handlePrevMonth}
                className="px-2.5 py-1 rounded transition-colors"
                style={{
                  backgroundColor: 'var(--tc-cell-default-bg)',
                  border: `1px solid var(--tc-cell-default-border)`,
                  color: 'var(--tc-secondary-text)',
                }}
              >
                &lt;
              </button>
              <button
                onClick={handleToday}
                className="px-2 py-1 rounded transition-colors text-xs"
                style={{
                  backgroundColor: 'var(--tc-cell-default-bg)',
                  border: `1px solid var(--tc-cell-default-border)`,
                  color: 'var(--tc-secondary-text)',
                }}
              >
                Today
              </button>
              <button
                onClick={handleNextMonth}
                className="px-2.5 py-1 rounded transition-colors"
                style={{
                  backgroundColor: 'var(--tc-cell-default-bg)',
                  border: `1px solid var(--tc-cell-default-border)`,
                  color: 'var(--tc-secondary-text)',
                }}
              >
                &gt;
              </button>
            </div>
          </div>
        </div>

        {/* Grid — 外層 overflow-x-auto：窄屏橫向捲動，嚴禁單元格擠壓溢出 */}
        <div className="overflow-x-auto">
          <div
            className="grid min-w-[560px] grid-cols-7 gap-2 font-mono"
            style={{ backgroundColor: 'var(--tc-card-bg)' }}
          >
          {weekDays.map((wd) => (
            <div
              key={wd}
              className="text-center py-1 text-xs font-semibold"
              style={{
                color: 'var(--tc-secondary-text)',
                borderBottom: `1px solid var(--tc-cell-default-border)`,
              }}
            >
              {wd}
            </div>
          ))}

          {calendarCells.map((cell, idx) => {
            if (!cell.dayNum || !cell.dateKey) {
              return (
                <div
                  key={`empty-${idx}`}
                  className="min-h-[76px] rounded-lg"
                  style={{
                    backgroundColor: 'var(--tc-cell-empty-bg)',
                    opacity: 0.3,
                  }}
                />
              );
            }

            const dayData = dailySummary[cell.dateKey];
            const hasTrade = dayData && dayData.totalCount > 0;
            const pnl = dayData?.totalPnl ?? 0;
            const winRate = hasTrade
              ? Math.round((dayData.winCount / dayData.totalCount) * 100)
              : 0;

            // ── 依據盈虧決定色系 ──
            let cellBg: string;
            let cellTextColor: string;
            let cellBorder: string;

            if (hasTrade) {
              if (pnl > 0) {
                cellBg = 'var(--tc-profit-bg)';
                cellTextColor = 'var(--tc-profit-text)';
                cellBorder = 'var(--tc-profit-border)';
              } else if (pnl < 0) {
                cellBg = 'var(--tc-loss-bg)';
                cellTextColor = 'var(--tc-loss-text)';
                cellBorder = 'var(--tc-loss-border)';
              } else {
                cellBg = 'var(--tc-cell-default-bg)';
                cellTextColor = 'var(--tc-main-text)';
                cellBorder = 'var(--tc-cell-default-border)';
              }
            } else {
              cellBg = 'var(--tc-cell-empty-bg)';
              cellTextColor = 'var(--tc-main-text)';
              cellBorder = 'var(--tc-cell-empty-border)';
            }

            const fmtPnl = (val: number) => {
              const absVal = Math.abs(val).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              });
              return val >= 0 ? `${currencySymbol}${absVal}` : `-${currencySymbol}${absVal}`;
            };

            return (
              <div
                key={cell.dateKey}
                className="flex min-w-0 flex-col items-center justify-center overflow-hidden min-h-[68px] rounded-lg border transition-all text-center"
                style={{
                  backgroundColor: cellBg,
                  borderColor: cell.isToday ? 'var(--tc-profit-text)' : cellBorder,
                  borderWidth: 1,
                  outline: cell.isToday ? `2px solid var(--tc-profit-text)` : 'none',
                  outlineOffset: '-2px',
                  padding: '6px 4px',
                }}
              >
                {/* 日期數字 */}
                <div
                  className="text-xs font-bold leading-tight sm:text-sm"
                  style={{
                    color: cell.isToday ? 'var(--tc-profit-text)' : 'var(--tc-secondary-text)',
                  }}
                >
                  {cell.dayNum}
                </div>

                {/* 內容區 */}
                {hasTrade ? (
                  mode === 'pnl' ? (
                    <div className="mt-0.5 w-full text-center leading-tight" style={{ color: cellTextColor }}>
                      <div className="whitespace-nowrap text-[10px] font-bold tabular-nums sm:text-xs lg:text-sm">{fmtPnl(pnl)}</div>
                      <div className="whitespace-nowrap text-[9px] tabular-nums sm:text-[10px]" style={{ opacity: 0.75 }}>{winRate}%</div>
                    </div>
                  ) : (
                    <div className="mt-0.5 w-full text-center leading-tight" style={{ color: cellTextColor }}>
                      <div className="whitespace-nowrap text-[10px] font-bold tabular-nums sm:text-xs lg:text-sm">{fmtPnl(pnl)}</div>
                      <div className="whitespace-nowrap text-[9px] tabular-nums sm:text-[10px]" style={{ opacity: 0.75 }}>
                        {dayData.winCount}W|{dayData.totalCount - dayData.winCount}L
                      </div>
                    </div>
                  )
                ) : null}
              </div>
            );
          })}
          </div>
        </div>
      </div>
    </Card>
  );
};
