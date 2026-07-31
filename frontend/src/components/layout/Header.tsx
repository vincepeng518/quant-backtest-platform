'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTheme } from 'next-themes';
import { Sun, Moon, Menu, X } from 'lucide-react';

export const Header: React.FC = () => {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);

  const navItems = [
    { name: 'Backtest', path: '/backtest' },
    { name: 'History', path: '/history' },
    { name: 'Optimize', path: '/optimize' },
    { name: 'Strategies', path: '/strategies' },
    { name: 'Trades', path: '/trades' },
  ];

  const isActive = (path: string) => pathname === path;

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border/50 bg-background/85 backdrop-blur-md">
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

        {/* Nav — desktop: mono index, gold underline on active */}
        <nav className="hidden md:flex flex-1 items-center justify-center gap-1 text-sm">
          {navItems.map((item) => {
            const active = isActive(item.path);
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
        </nav>

        {/* Right controls */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="flex h-11 w-11 items-center justify-center text-textSecondary transition-colors hover:text-accent"
            aria-label="Toggle theme"
          >
            <Sun className="h-4 w-4 dark:hidden" />
            <Moon className="h-4 w-4 hidden dark:block" />
          </button>
          {/* Hamburger — mobile only */}
          <button
            onClick={() => setOpen((v) => !v)}
            className="flex h-11 w-11 items-center justify-center text-textSecondary transition-colors hover:text-accent md:hidden"
            aria-label={open ? 'Close menu' : 'Open menu'}
            aria-expanded={open}
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile drawer */}
      {open && (
        <nav className="border-t border-border/50 bg-background/95 backdrop-blur-md md:hidden">
          {navItems.map((item) => {
            const active = isActive(item.path);
            return (
              <Link
                key={item.path}
                href={item.path}
                onClick={() => setOpen(false)}
                className={`flex h-12 items-center justify-between px-5 font-mono text-sm uppercase tracking-wider transition-colors ${
                  active
                    ? 'bg-accent/10 text-accent'
                    : 'text-textSecondary hover:bg-surface hover:text-text'
                }`}
              >
                {item.name}
                {active && <span className="h-1.5 w-1.5 bg-accent" />}
              </Link>
            );
          })}
        </nav>
      )}
    </header>
  );
};
