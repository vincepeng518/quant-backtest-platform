import React from 'react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: { label: string; value: string | number; group?: string }[];
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
                'w-full cursor-pointer appearance-none rounded-lg border border-white/[0.1] bg-surface/90 py-2.5 pl-3.5 pr-9 text-sm text-text transition-all duration-150 ease-out hover:border-white/[0.2] focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40 shadow-inner'
              ),
              className
            )}
            {...props}
          >
            {(() => {
            const groups = new Map<string, typeof options>();
            const ungrouped: typeof options = [];
            for (const opt of options) {
              if (opt.group) {
                const g = groups.get(opt.group) || [];
                g.push(opt);
                groups.set(opt.group, g);
              } else {
                ungrouped.push(opt);
              }
            }
            if (groups.size === 0) {
              return options.map((opt) => (
                <option key={opt.value} value={opt.value} className="bg-surface text-text">
                  {opt.label}
                </option>
              ));
            }
            const out: React.ReactNode[] = [];
            if (ungrouped.length > 0) {
              out.push(<optgroup key="_ungrouped" label="─">
                {ungrouped.map((opt) => (
                  <option key={opt.value} value={opt.value} className="bg-surface text-text">{opt.label}</option>
                ))}
              </optgroup>);
            }
            groups.forEach((g, name) => {
              out.push(<optgroup key={name} label={name}>
                {g.map((opt) => (
                  <option key={opt.value} value={opt.value} className="bg-surface text-text">{opt.label}</option>
                ))}
              </optgroup>);
            });
            return out;
          })()}
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
