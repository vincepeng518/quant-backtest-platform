import React from 'react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = 'text', label, error, ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label className="block text-xs font-medium text-textSecondary uppercase tracking-wider mb-2">
            {label}
          </label>
        )}
        <input
          type={type}
          className={twMerge(
            clsx(
              // Minimal single baseline bottom border, no border stroke boxes, monospace numbers
              'w-full rounded-md border border-border/40 bg-surface px-3 py-2 text-sm text-text placeholder:text-textSecondary/50 transition-all duration-150 ease-out focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/30 font-mono'
            ),
            className
          )}
          ref={ref}
          {...props}
        />
        {error && <p className="mt-1.5 text-xs text-danger font-normal">{error}</p>}
      </div>
    );
  }
);

Input.displayName = 'Input';
