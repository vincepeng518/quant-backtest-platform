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

  // 依日期 (YYYY-MM-DD) Group By 彙整 PnL 與交易筆數
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

  // 切換月份
  const handlePrevMonth = () => {
    setCurrentDate(new Date(year, month - 1, 1));
  };

  const handleNextMonth = () => {
    setCurrentDate(new Date(year, month + 1, 1));
  };

  const handleToday = () => {
    setCurrentDate(new Date());
  };

  // 生成當月日曆網格 (包含前置空白)
  const calendarCells = useMemo(() => {
    const firstDayOfWeek = new Date(year, month, 1).getDay(); // 0 = SUN
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    const cells: Array<{
      dayNum: number | null;
      dateKey: string | null;
      isToday: boolean;
    }> = [];

    // 填充第一天之前的空白格
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

  return (
    <Card className="p-5 space-y-4">
      {/* 頂部 Header 控制列 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/20 pb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold font-sans text-text">Trading Calendar</h2>
          {/* PNL / Events 模式切換 */}
          <div className="flex items-center bg-surface p-1 rounded-lg border border-border/30 text-xs font-mono">
            <button
              onClick={() => setMode('pnl')}
              className={`px-3 py-1 rounded-md transition-colors ${
                mode === 'pnl'
                  ? 'bg-accent text-background font-medium'
                  : 'text-textSecondary hover:text-text'
              }`}
            >
              PNL
            </button>
            <button
              onClick={() => setMode('events')}
              className={`px-3 py-1 rounded-md transition-colors ${
                mode === 'events'
                  ? 'bg-accent text-background font-medium'
                  : 'text-textSecondary hover:text-text'
              }`}
            >
              Events
            </button>
          </div>
        </div>

        {/* 月份切換與年月顯示 */}
        <div className="flex items-center gap-2 font-mono text-sm">
          <span className="font-bold text-text px-2">{monthLabel}</span>
          <div className="flex items-center gap-1">
            <button
              onClick={handlePrevMonth}
              className="px-2.5 py-1 rounded bg-surface hover:bg-surface/80 border border-border/30 text-textSecondary hover:text-text transition-colors"
              title="上一月"
            >
              &lt;
            </button>
            <button
              onClick={handleToday}
              className="px-2 py-1 rounded bg-surface hover:bg-surface/80 border border-border/30 text-xs text-textSecondary hover:text-text transition-colors"
            >
              Today
            </button>
            <button
              onClick={handleNextMonth}
              className="px-2.5 py-1 rounded bg-surface hover:bg-surface/80 border border-border/30 text-textSecondary hover:text-text transition-colors"
              title="下一月"
            >
              &gt;
            </button>
          </div>
        </div>
      </div>

      {/* 7 欄 CSS Grid 日曆網格 */}
      <div className="grid grid-cols-7 gap-1.5 font-mono">
        {/* 星期 Header */}
        {weekDays.map((wd) => (
          <div
            key={wd}
            className="text-center py-1 text-xs font-semibold text-textSecondary border-b border-border/10"
          >
            {wd}
          </div>
        ))}

        {/* 日期格子 */}
        {calendarCells.map((cell, idx) => {
          if (!cell.dayNum || !cell.dateKey) {
            return (
              <div
                key={`empty-${idx}`}
                className="min-h-[76px] rounded-lg bg-surface/20 opacity-30"
              />
            );
          }

          const dayData = dailySummary[cell.dateKey];
          const hasTrade = dayData && dayData.totalCount > 0;
          const pnl = dayData?.totalPnl ?? 0;

          // 計算勝率
          const winRate = hasTrade
            ? Math.round((dayData.winCount / dayData.totalCount) * 100)
            : 0;

          let bgClass = 'bg-surface/50 border-border/20 hover:border-border/50';
          if (hasTrade) {
            if (pnl > 0) {
              // 綠色獲利風格
              bgClass =
                'bg-emerald-950/60 dark:bg-emerald-950/80 border-emerald-500/40 text-emerald-400';
            } else if (pnl < 0) {
              // 紅色虧損風格
              bgClass =
                'bg-rose-950/60 dark:bg-rose-950/80 border-rose-500/40 text-rose-400';
            } else {
              bgClass = 'bg-surface border-border/40 text-text';
            }
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
              className={`min-h-[76px] p-2 rounded-lg border transition-all flex flex-col justify-between ${bgClass} ${
                cell.isToday ? 'ring-2 ring-accent' : ''
              }`}
            >
              {/* 頂部：日期數字 */}
              <div className="flex justify-between items-start">
                <span
                  className={`text-xs font-bold ${
                    cell.isToday ? 'text-accent' : 'text-textSecondary'
                  }`}
                >
                  {cell.dayNum}
                </span>
                {hasTrade && mode === 'events' && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface/80 text-textSecondary">
                    {dayData.totalCount} 筆
                  </span>
                )}
              </div>

              {/* 中央/底部：根據模式與資料顯示 */}
              {hasTrade ? (
                mode === 'pnl' ? (
                  <div className="mt-1 space-y-0.5">
                    <div className="text-xs font-bold truncate">
                      {fmtPnl(pnl)}
                    </div>
                    <div className="text-[10px] opacity-80 flex justify-between items-center">
                      <span>勝率</span>
                      <span className="font-semibold">{winRate}%</span>
                    </div>
                  </div>
                ) : (
                  <div className="mt-1 text-[11px] font-mono space-y-0.5">
                    <div className="truncate font-semibold">{fmtPnl(pnl)}</div>
                    <div className="text-[10px] opacity-75">
                      {dayData.winCount}勝 / {dayData.totalCount - dayData.winCount}負
                    </div>
                  </div>
                )
              ) : (
                <div className="text-[10px] text-textSecondary/30 select-none">-</div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
};
