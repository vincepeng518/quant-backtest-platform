'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTheme } from 'next-themes';
import { Sun, Moon, Database, Activity, TrendingUp, Sliders } from 'lucide-react';

export const Header: React.FC = () => {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();

  const navItems = [
    { name: 'Backtest', path: '/backtest', icon: Activity },
    { name: 'Optimize', path: '/optimize', icon: Sliders },
    { name: 'Analysis', path: '/analysis', icon: TrendingUp },
  ];

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border/40 bg-background/80 backdrop-blur-md">
      <div className="flex h-14 items-center justify-between px-6 max-w-7xl mx-auto">
        {/* Brand System Logo */}
        <Link href="/" className="flex items-center space-x-2 font-semibold tracking-tight text-sm">
          <Database className="h-4 w-4 text-accent" />
          <span className="font-mono">QUANT.LAB</span>
        </Link>

        {/* Minimal Navigation items */}
        <nav className="flex items-center space-x-8 text-sm">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.path || (item.path === '/backtest' && pathname === '/');
            return (
              <Link
                key={item.path}
                href={item.path}
                className={`flex items-center space-x-1.5 transition-colors duration-150 ${
                  active
                    ? 'text-text font-medium'
                    : 'text-textSecondary hover:text-text font-normal'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                <span>{item.name}</span>
              </Link>
            );
          })}
        </nav>

        {/* Global Action Tools Section */}
        <div className="flex items-center space-x-4">
          <button
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="p-1 rounded text-textSecondary hover:text-text transition-colors"
          >
            <Sun className="h-4 w-4 dark:hidden" />
            <Moon className="h-4 w-4 hidden dark:block" />
          </button>
        </div>
      </div>
    </header>
  );
};
