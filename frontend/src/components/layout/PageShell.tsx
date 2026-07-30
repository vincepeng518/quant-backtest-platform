import React, { useEffect } from 'react';

interface PageShellProps {
  /** mono uppercase kicker above the title, e.g. "BACKTEST / workflow" */
  eyebrow?: string;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}

/**
 * Shared page scaffolding for the Quant Platform:
 * mono kicker with accent tick, display title, accent hairline rule beneath.
 * Every functional page wraps in this so the whole app reads as one system.
 */
export const PageShell: React.FC<PageShellProps> = ({
  eyebrow,
  title,
  subtitle,
  children,
}) => {
  useEffect(() => {
    document.title = `${title} — Quant Backtest`;
  }, [title]);

  return (
    <div className="max-w-7xl mx-auto px-4 md:px-6 py-10 md:py-14">
      <header className="mb-10 md:mb-14">
        {eyebrow && (
          <div className="mb-3 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.2em] text-textSecondary">
            <span className="h-1.5 w-1.5 bg-accent" />
            <span>{eyebrow}</span>
          </div>
        )}
        <h1 className="font-display text-3xl font-semibold leading-[1.1] tracking-tight md:text-4xl">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-textSecondary md:text-base">
            {subtitle}
          </p>
        )}
        <div className="accent-rule mt-6" />
      </header>

      <div className="space-y-8">{children}</div>
    </div>
  );
};
