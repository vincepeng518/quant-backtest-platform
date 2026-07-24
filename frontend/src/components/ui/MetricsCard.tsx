'use client';

import React from 'react';

type MetricAccent = 'success' | 'danger' | 'neutral' | 'accent';

interface MetricItem {
  label: string;
  value: string | number;
  accent?: MetricAccent;
}

interface MetricsCardProps {
  items: MetricItem[];
  className?: string;
}

const ACCENT_CLASS: Record<MetricAccent, string> = {
  success: 'text-success',
  danger: 'text-danger',
  accent: 'text-accent',
  neutral: 'text-text',
};

export const MetricsCard: React.FC<MetricsCardProps> = ({ items, className = '' }) => {
  return (
    <div className={`bg-surface border border-border/40 p-6 select-none ${className}`}>
      <div className="mb-4 flex items-center gap-2">
        <span className="h-1.5 w-1.5 bg-accent" />
        <h3 className="font-mono text-xs font-medium uppercase tracking-wider text-textSecondary">
          Results Summary
        </h3>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-px bg-border/30">
        {items.map((item) => (
          <div key={item.label} className="flex flex-col justify-between bg-surface p-4">
            <span className="font-mono text-[11px] uppercase tracking-wider text-textSecondary">
              {item.label}
            </span>
            <span
              className={`mt-2 font-mono text-2xl font-semibold tracking-tight ${
                ACCENT_CLASS[item.accent ?? 'neutral']
              }`}
            >
              {item.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
