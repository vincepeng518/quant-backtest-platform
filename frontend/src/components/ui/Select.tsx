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
          <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-textSecondary">
            {label}
          </label>
        )}
        <div className="relative w-full overflow-hidden">
          <select
            ref={ref}
            className={twMerge(
              clsx(
                'w-full cursor-pointer appearance-none border-b border-border/60 bg-transparent py-1.5 pr-8 text-sm text-text duration-150 ease-out focus:border-accent focus:outline-none'
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
          {/* Pure CSS chevron — no SVG that can scale with parent */}
          <span
            aria-hidden
            className="pointer-events-none absolute right-1 top-1/2 block h-2 w-2 -translate-y-[35%] rotate-45 border-b border-r border-textSecondary"
          />
        </div>
        {error && <p className="mt-1.5 text-xs text-danger">{error}</p>}
      </div>
    );
  }
);

Select.displayName = 'Select';
