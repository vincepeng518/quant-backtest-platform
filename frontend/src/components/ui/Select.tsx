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
        <div className="relative w-full">
          <select
            ref={ref}
            className={twMerge(
              clsx(
                // Impeccable: underline select, no native arrow, room for custom chevron
                'w-full cursor-pointer appearance-none border-b border-border/60 bg-transparent py-1.5 pr-7 text-sm text-text duration-150 ease-out focus:border-accent focus:outline-none'
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

          {/* fixed 16px chevron — never inherit layout size */}
          <span
            aria-hidden
            className="pointer-events-none absolute right-0 top-1/2 flex h-4 w-4 -translate-y-1/2 items-center justify-center text-textSecondary"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              className="block h-4 w-4 shrink-0"
              style={{ width: 16, height: 16, maxWidth: 16, maxHeight: 16 }}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </span>
        </div>
        {error && <p className="mt-1.5 text-xs text-danger">{error}</p>}
      </div>
    );
  }
);

Select.displayName = 'Select';
