'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import clsx from 'clsx';
import { sectorOf, SECTOR_GROUPS, type Sector } from '@/lib/symbolCatalog';

interface SymbolSearchProps {
  label?: string;
  value: string;
  options: { symbol: string }[];
  onChange: (symbol: string) => void;
  placeholder?: string;
}

const FAV_KEY = 'fav_symbols';
const SECTORS: string[] = ['主流', 'Meme', 'DeFi', 'AI', 'Layer2', '其他', '收藏'];

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

  const allSyms = useMemo(() => options.map((o) => o.symbol), [options]);

  const toggleFav = (s: string) => {
    setFavs((prev) => {
      const next = prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s];
      try { localStorage.setItem(FAV_KEY, JSON.stringify(next)); } catch {}
      return next;
    });
  };

  const q = query.trim().toUpperCase();

  const list = useMemo(() => {
    let pool = allSyms;
    if (tab === '收藏') pool = favs;
    else if (tab !== '其他') pool = allSyms.filter((s) => sectorOf(s) === tab);
    // 其他: 不被任何分類覆蓋的
    else pool = allSyms.filter((s) => sectorOf(s) === '其他');

    if (q) pool = pool.filter((s) => s.includes(q));
    return Array.from(new Set(pool)).slice(0, 80);
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
                  <div key={s} className="flex items-center justify-between px-1">
                    <button
                      type="button"
                      onClick={() => commit(s)}
                      className={clsx(
                        'block flex-1 px-2 py-1.5 text-left text-sm hover:bg-accent/10',
                        s === value ? 'text-accent' : 'text-text'
                      )}
                    >
                      {s}
                      <span className="ml-2 text-[10px] text-textSecondary">{sectorOf(s)}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => toggleFav(s)}
                      title="收藏"
                      className={clsx(
                        'px-2 py-1.5 text-xs',
                        favs.includes(s) ? 'text-yellow-400' : 'text-textSecondary hover:text-yellow-400'
                      )}
                    >
                      {favs.includes(s) ? '★' : '☆'}
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
