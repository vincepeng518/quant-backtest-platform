import React from 'react';

interface PageShellProps {
  /** mono uppercase eyebrow above the title, e.g. "BACKTEST / workflow" */
  eyebrow?: string;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}

/**
 * Shared page scaffolding that mirrors the homepage's premium feel:
 * max-width container, generous vertical rhythm, and a hero header with a
 * mono eyebrow + accent glow. Every functional page wraps in this so the
 * whole app reads as one designed system.
 */
export const PageShell: React.FC<PageShellProps> = ({
  eyebrow,
  title,
  subtitle,
  children,
}) => {
  return (
    <div className="max-w-7xl mx-auto px-4 md:px-6 py-10 md:py-14">
      {/* Hero header */}
      <header className="relative mb-10 md:mb-14">
        <div className="pointer-events-none absolute -top-10 -left-4 -z-10 h-48 w-48 rounded-full bg-accent/5 blur-3xl" />
        {eyebrow && (
          <div className="mb-4 flex items-center space-x-2 font-mono text-xs uppercase tracking-[0.2em] text-textSecondary">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            <span>{eyebrow}</span>
          </div>
        )}
        <h1 className="text-3xl font-semibold leading-[1.1] tracking-tight md:text-4xl">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-textSecondary md:text-base">
            {subtitle}
          </p>
        )}
      </header>

      <div className="space-y-8">{children}</div>
    </div>
  );
};
