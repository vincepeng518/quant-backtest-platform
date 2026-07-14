'use client';

import React, { useEffect, useRef, useState } from 'react';
import clsx from 'clsx';

interface SymbolSearchProps {
  label?: string;
  value: string;
  options: { symbol: string }[];
  onChange: (symbol: string) => void;
  placeholder?: string;
}

export const SymbolSearch: React.FC<SymbolSearchProps> = ({
  label,
  value,
  options,
  onChange,
  placeholder = 'Search e.g. BTC/USDT …',
}) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const wrapRef = useRef<HTMLDivElement>(null);

  // 关闭点击外部
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const q = query.trim().toUpperCase();
  const filtered = q
    ? options.filter((o) => o.symbol.includes(q)).slice(0, 60)
    : options.slice(0, 60);

  const commit = (sym: string) => {
    const s = sym.trim().toUpperCase();
    if (!s) return;
    onChange(s);
    setQuery('');
    setOpen(false);
  };

  return (
    <div className="w-full min-w-0">
      {label && (
        <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-textSecondary">
          {label}
        </label>
      )}
      <div ref={wrapRef} className="relative w-full">
        <input
          value={open ? query : value}
          onFocus={() => {
            setOpen(true);
            setQuery('');
          }}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              commit(query || value);
            } else if (e.key === 'Escape') {
              setOpen(false);
            }
          }}
          placeholder={placeholder}
          spellCheck={false}
          className="w-full border-b border-border/60 bg-transparent py-1.5 pr-8 text-sm text-text duration-150 ease-out focus:border-accent focus:outline-none placeholder:text-textSecondary/50"
        />
        {/* chevron */}
        <button
          type="button"
          tabIndex={-1}
          onClick={() => setOpen((v) => !v)}
          className="pointer-events-none absolute right-1 top-1/2 block h-2 w-2 -translate-y-[35%] rotate-45 border-b border-r border-textSecondary"
          aria-hidden
        />
        {open && (
          <div className="absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-md border border-border/40 bg-surface py-1 shadow-xl">
            {filtered.length === 0 ? (
              <div className="px-3 py-2 text-xs text-textSecondary">
                無匹配 — 直接輸入 <span className="font-mono text-text">SYM/USDT</span> 後按 Enter
              </div>
            ) : (
              filtered.map((o) => (
                <button
                  key={o.symbol}
                  type="button"
                  onClick={() => commit(o.symbol)}
                  className={clsx(
                    'block w-full px-3 py-1.5 text-left text-sm hover:bg-accent/10',
                    o.symbol === value ? 'text-accent' : 'text-text'
                  )}
                >
                  {o.symbol}
                </button>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
};
