'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTheme } from 'next-themes';
import { Sun, Moon, Database, Activity, TrendingUp, Sliders, Code2, HardDrive, History, FlaskConical, Settings } from 'lucide-react';

export const Header: React.FC = () => {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();

  const navItems = [
    { name: 'Backtest', path: '/backtest', icon: Activity },
    { name: 'Optimize', path: '/optimize', icon: Sliders },
    { name: 'Analysis', path: '/analysis', icon: TrendingUp },
    { name: 'Strategies', path: '/strategies', icon: Code2 },
    { name: 'Data', path: '/data', icon: HardDrive },
    { name: 'History', path: '/history', icon: History },
    { name: 'Research', path: '/research', icon: FlaskConical },
    { name: 'Admin', path: '/admin', icon: Settings },
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
        <nav className="flex flex-1 items-center justify-center space-x-1 sm:space-x-6 text-sm overflow-x-auto no-scrollbar">
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
