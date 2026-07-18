'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import clsx from 'clsx';
import { sectorOf, SECTOR_GROUPS, type Sector } from '@/lib/symbolCatalog';

interface SymbolSearchProps {
  label?: string;
  value: string;
  options: { symbol: string; status?: string; category?: string }[];
  onChange: (symbol: string) => void;
  placeholder?: string;
}

const FAV_KEY = 'fav_symbols';
const SECTORS: string[] = ['fx', 'metal', 'energy', 'index', 'stock', '其他', '收藏'];

export const SymbolSearch: React.FC<SymbolSearchProps> = ({
  label,
  value,
  options,
  onChange,
  placeholder = 'Search e.g. BTC/USDT …',
}) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState<string>('主流');
  const [favs, setFavs] = useState<string[]>([]);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(FAV_KEY);
      if (saved) setFavs(JSON.parse(saved));
    } catch {}
  }, []);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const allSyms = useMemo(
    () => options.map((o) => ({ symbol: o.symbol, status: o.status, category: o.category })),
    [options]
  );

  const statusBadge = (st?: string) => {
    if (st === 'paused') return <span className="ml-1 rounded bg-yellow-500/15 px-1 text-[9px] text-yellow-400">暫停</span>;
    if (st === 'offline') return <span className="ml-1 rounded bg-red-500/15 px-1 text-[9px] text-red-400">下線</span>;
    if (st === 'not_exist') return <span className="ml-1 rounded bg-gray-500/15 px-1 text-[9px] text-gray-400">無</span>;
    return null;
  };

  const isDisabled = (st?: string) => st === 'offline' || st === 'not_exist';

  const toggleFav = (s: string) => {
    setFavs((prev) => {
      const next = prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s];
      try { localStorage.setItem(FAV_KEY, JSON.stringify(next)); } catch {}
      return next;
    });
  };

  const q = query.trim().toUpperCase();

  const list = useMemo((): { symbol: string; status?: string; category?: string }[] => {
    let pool: { symbol: string; status?: string; category?: string }[] = allSyms;
    if (tab === '收藏') pool = favs.map((s) => allSyms.find((x) => x.symbol === s)).filter(Boolean) as typeof allSyms;
    else if (tab !== '其他') pool = allSyms.filter((s) => (s.category || '其他') === tab);
    else pool = allSyms.filter((s) => !s.category || s.category === '其他');

    if (q) pool = pool.filter((s) => s.symbol.includes(q));
    const uniq = Array.from(new Set(pool.map((p) => p.symbol))).map((sym) => pool.find((p) => p.symbol === sym)!);
    return uniq.slice(0, 80);
  }, [allSyms, tab, q, favs]);

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
          onFocus={() => { setOpen(true); setQuery(''); }}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit(query || value);
            else if (e.key === 'Escape') setOpen(false);
          }}
          placeholder={placeholder}
          spellCheck={false}
          className="w-full border-b border-border/60 bg-transparent py-1.5 pr-8 text-sm text-text duration-150 ease-out focus:border-accent focus:outline-none placeholder:text-textSecondary/50"
        />
        <button
          type="button" tabIndex={-1} onClick={() => setOpen((v) => !v)}
          className="pointer-events-none absolute right-1 top-1/2 block h-2 w-2 -translate-y-[35%] rotate-45 border-b border-r border-textSecondary"
          aria-hidden
        />
        {open && (
          <div className="absolute z-30 mt-1 w-full rounded-md border border-border/40 bg-surface shadow-xl">
            {/* 板块 Tabs */}
            <div className="flex flex-wrap gap-1 border-b border-border/30 px-2 py-1.5">
              {SECTORS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setTab(s)}
                  className={clsx(
                    'rounded px-2 py-0.5 text-xs',
                    tab === s ? 'bg-accent text-white' : 'text-textSecondary hover:bg-accent/10'
                  )}
                >
                  {s}
                  {s === '收藏' && favs.length > 0 ? ` (${favs.length})` : ''}
                </button>
              ))}
            </div>
            {/* 列表 */}
            <div className="max-h-64 overflow-auto py-1">
              {list.length === 0 ? (
                <div className="px-3 py-2 text-xs text-textSecondary">
                  無匹配 — 直接輸入 <span className="font-mono text-text">SYM/USDT</span> 後按 Enter
                </div>
              ) : (
                list.map((s) => (
                  <div key={s.symbol} className="flex items-center justify-between px-1">
                    <button
                      type="button"
                      disabled={isDisabled(s.status)}
                      onClick={() => !isDisabled(s.status) && commit(s.symbol)}
                      className={clsx(
                        'block flex-1 px-2 py-1.5 text-left text-sm hover:bg-accent/10',
                        s.symbol === value ? 'text-accent' : 'text-text',
                        isDisabled(s.status) && 'cursor-not-allowed opacity-40 hover:bg-transparent'
                      )}
                    >
                      {s.symbol}
                      {statusBadge(s.status)}
                      {s.category && s.status === 'active' && (
                        <span className="ml-1 text-[10px] text-textSecondary">{s.category}</span>
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => toggleFav(s.symbol)}
                      title="收藏"
                      className={clsx(
                        'px-2 py-1.5 text-xs',
                        favs.includes(s.symbol) ? 'text-yellow-400' : 'text-textSecondary hover:text-yellow-400'
                      )}
                    >
                      {favs.includes(s.symbol) ? '★' : '☆'}
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
