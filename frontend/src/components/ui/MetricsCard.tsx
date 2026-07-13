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
    <div
      className={`bg-surface border-t border-border/10 p-6 select-none ${className}`}
    >
      <h3 className="text-sm font-semibold uppercase tracking-wider text-accent mb-4">
        Results Summary
      </h3>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {items.map((item) => (
          <div
            key={item.label}
            className="flex flex-col justify-between bg-background/40 rounded-md p-3 border border-border/10"
          >
            <span className="text-xs font-medium text-textSecondary uppercase tracking-wider">
              {item.label}
            </span>
            <span
              className={`mt-2 text-2xl font-mono font-semibold tracking-tight ${
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
