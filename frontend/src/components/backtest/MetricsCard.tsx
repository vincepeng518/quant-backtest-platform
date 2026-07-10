'use client';

import React from 'react';

interface MetricsCardProps {
  label: string;
  value: string | number;
  change?: string;
  color?: 'positive' | 'negative' | 'neutral';
}

export const MetricsCard: React.FC<MetricsCardProps> = ({
  label,
  value,
  change,
  color = 'neutral',
}) => {
  return (
    <div className="bg-surface p-6 border-t border-border/10 flex flex-col justify-between select-none">
      <span className="text-xs font-medium text-textSecondary uppercase tracking-wider">
        {label}
      </span>
      <div className="flex items-baseline justify-between mt-4">
        <span className="text-2xl font-mono font-semibold tracking-tight text-text">
          {value}
        </span>
        {change && (
          <span
            className={`text-xs font-mono font-medium ${
              color === 'positive' ? 'text-success' : color === 'negative' ? 'text-danger' : 'text-textSecondary'
            }`}
          >
            {change}
          </span>
        )}
      </div>
    </div>
  );
};
