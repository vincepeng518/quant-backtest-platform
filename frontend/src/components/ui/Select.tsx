import React from 'react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: { label: string; value: string | number }[];
  error?: string;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, label, options, error, ...props }, ref) => {
    return (
      <div className="w-full min-w-0">
        {label && (
          <label className="mb-2 block text-xs font-medium tracking-wider text-textSecondary">
            {label}
          </label>
        )}
        <div className="relative w-full">
          <select
            ref={ref}
            className={twMerge(
              clsx(
                'w-full cursor-pointer appearance-none rounded-md border border-border/40 bg-surface py-2 pl-3 pr-9 text-sm text-text transition-all duration-150 ease-out hover:border-border/60 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/30'
              ),
              className
            )}
            {...props}
          >
            {options.map((opt) => (
              <option key={opt.value} value={opt.value} className="bg-surface text-text">
                {opt.label}
              </option>
            ))}
          </select>
          <span
            aria-hidden
            className="pointer-events-none absolute right-2.5 top-1/2 block h-1.5 w-1.5 -translate-y-1/2 rotate-45 border-b border-r border-textSecondary"
          />
        </div>
        {error && <p className="mt-1.5 text-xs text-danger">{error}</p>}
      </div>
    );
  }
);

Select.displayName = 'Select';
