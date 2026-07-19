'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTheme } from 'next-themes';
import { Sun, Moon, Database, Activity, TrendingUp, Sliders, Code2, HardDrive, History, FlaskConical, Settings, Wallet, ChevronDown, LineChart } from 'lucide-react';

export const Header: React.FC = () => {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const [moreOpen, setMoreOpen] = useState(false);

  const navItems = [
    { name: 'Dashboard', path: '/', icon: Database },
    { name: 'Backtest', path: '/backtest', icon: Activity },
    { name: 'Analysis', path: '/analysis', icon: TrendingUp },
    { name: 'Strategies', path: '/strategies', icon: Code2 },
    { name: 'Trades', path: '/trades', icon: Wallet },
    { name: 'Admin', path: '/admin', icon: Settings },
  ];

  // 子功能 (收納於「更多」)
  const subItems = [
    { name: 'Optimize', path: '/optimize', icon: Sliders, parent: 'Backtest' },
    { name: 'Research', path: '/research', icon: FlaskConical, parent: 'Backtest' },
    { name: 'Data', path: '/data', icon: HardDrive, parent: 'Strategies' },
    { name: 'History', path: '/history', icon: History, parent: 'Trades' },
    { name: 'Monitoring', path: '/monitoring', icon: LineChart, parent: 'Dashboard' },
    { name: 'Arbitrage', path: '/arbitrage', icon: LineChart, parent: 'Admin' },
    { name: 'Experiments', path: '/experiments', icon: FlaskConical, parent: 'Admin' },
  ];

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border/40 bg-background/80 backdrop-blur-md">
      <div className="flex h-14 items-center justify-between gap-4 px-4 md:px-6 max-w-7xl mx-auto">
        {/* Brand */}
        <Link href="/" className="flex shrink-0 items-center space-x-2 font-semibold tracking-tight text-sm">
          <Database className="h-4 w-4 shrink-0 text-accent" />
          <span className="font-mono whitespace-nowrap">QUANT.LAB</span>
        </Link>

        {/* Nav */}
        <nav className="flex flex-1 items-center justify-center space-x-1 sm:space-x-2 text-sm overflow-x-auto no-scrollbar">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.path || (item.path === '/backtest' && pathname === '/');
            return (
              <Link
                key={item.path}
                href={item.path}
                className={`flex shrink-0 items-center space-x-1.5 rounded-md px-2 py-1 transition-colors duration-150 ${
                  active
                    ? 'text-text font-medium bg-surface'
                    : 'text-textSecondary hover:text-text font-normal'
                }`}
              >
                <Icon className="h-3.5 w-3.5 shrink-0" />
                <span className="whitespace-nowrap">{item.name}</span>
              </Link>
            );
          })}

          {/* 更多 (子功能) */}
          <div className="relative shrink-0">
            <button
              onClick={() => setMoreOpen((v) => !v)}
              onBlur={() => setTimeout(() => setMoreOpen(false), 150)}
              className={`flex items-center space-x-1 rounded-md px-2 py-1 transition-colors ${
                subItems.some((s) => pathname === s.path)
                  ? 'text-text font-medium bg-surface'
                  : 'text-textSecondary hover:text-text'
              }`}
            >
              <span className="whitespace-nowrap">更多</span>
              <ChevronDown className="h-3.5 w-3.5" />
            </button>
            {moreOpen && (
              <div className="absolute right-0 z-50 mt-1 w-48 rounded-md border border-border/40 bg-background shadow-lg py-1">
                {subItems.map((s) => {
                  const Icon = s.icon;
                  const active = pathname === s.path;
                  return (
                    <Link
                      key={s.path}
                      href={s.path}
                      className={`flex items-center space-x-2 px-3 py-1.5 text-sm ${
                        active ? 'text-text bg-surface' : 'text-textSecondary hover:text-text hover:bg-surface/60'
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5 shrink-0" />
                      <span className="flex-1">{s.name}</span>
                      <span className="text-[10px] text-textSecondary/60">{s.parent}</span>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        </nav>

        {/* Theme toggle */}
        <button
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          className="shrink-0 p-1 rounded text-textSecondary hover:text-text transition-colors"
          aria-label="Toggle theme"
        >
          <Sun className="h-4 w-4 dark:hidden" />
          <Moon className="h-4 w-4 hidden dark:block" />
        </button>
      </div>
    </header>
  );
};
