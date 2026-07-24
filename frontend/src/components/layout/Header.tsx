'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTheme } from 'next-themes';
import { Sun, Moon } from 'lucide-react';

export const Header: React.FC = () => {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();

  const navItems = [
    { name: 'Backtest', path: '/backtest' },
    { name: 'History', path: '/history' },
    { name: 'Optimize', path: '/optimize' },
    { name: 'Strategies', path: '/strategies' },
    { name: 'Trades', path: '/trades' },
  ];

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border/50 bg-background/85 backdrop-blur-md">
      <div className="gold-rule" />
      <div className="flex h-14 items-center justify-between gap-4 px-4 md:px-6 max-w-7xl mx-auto">
        {/* Brand */}
        <Link href="/" className="group flex shrink-0 items-center gap-2.5">
          <span className="flex h-6 w-6 items-center justify-center border border-accent/40 bg-accent/10 transition-colors group-hover:bg-accent/20">
            <span className="h-2 w-2 bg-accent" />
          </span>
          <span className="font-display text-sm font-semibold tracking-tight whitespace-nowrap">
            QUANT<span className="text-accent">.LAB</span>
          </span>
        </Link>

        {/* Nav — mono index, gold underline on active */}
        <nav className="flex flex-1 items-center justify-center gap-1 overflow-x-auto no-scrollbar text-sm">
          {navItems.map((item) => {
            const active =
              pathname === item.path || (item.path === '/backtest' && pathname === '/');
            return (
              <Link
                key={item.path}
                href={item.path}
                className={`relative shrink-0 whitespace-nowrap px-2.5 py-1.5 font-mono text-xs uppercase tracking-wider transition-colors duration-150 ${
                  active ? 'text-accent' : 'text-textSecondary hover:text-text'
                }`}
              >
                {item.name}
                {active && (
                  <span className="absolute bottom-0 left-2.5 right-2.5 h-px bg-accent" />
                )}
              </Link>
            );
          })}
          <a
            href="/llmlite-ui.html"
            target="_self"
            className="shrink-0 whitespace-nowrap px-2.5 py-1.5 font-mono text-xs uppercase tracking-wider text-accent/70 transition-colors hover:text-accent"
          >
            LLMLite
          </a>
        </nav>

        {/* Theme toggle */}
        <button
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          className="shrink-0 p-1.5 text-textSecondary transition-colors hover:text-accent"
          aria-label="Toggle theme"
        >
          <Sun className="h-4 w-4 dark:hidden" />
          <Moon className="h-4 w-4 hidden dark:block" />
        </button>
      </div>
    </header>
  );
};
