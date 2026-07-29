import React from 'react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
}

export const Button: React.FC<ButtonProps> = ({
  children,
  className,
  variant = 'primary',
  size = 'md',
  ...props
}) => {
  return (
    <button
      className={twMerge(
        clsx(
          'inline-flex items-center justify-center font-medium rounded-md transition-all duration-150 ease-out focus:outline-none focus:ring-1 focus:ring-accent/30 disabled:opacity-50 disabled:pointer-events-none active:scale-[0.97]',
          {
            'bg-gradient-to-r from-sky-400 to-blue-600 text-slate-950 font-semibold shadow-[0_0_20px_rgba(56,189,248,0.3)] hover:shadow-[0_0_25px_rgba(56,189,248,0.5)] hover:from-sky-300 hover:to-blue-500': variant === 'primary',
            'bg-surface2/80 text-text border border-white/[0.1] hover:bg-surface2 hover:border-white/[0.2]': variant === 'secondary',
            'text-textSecondary hover:text-text hover:bg-surface2/60': variant === 'ghost',
          },
          {
            'px-2.5 py-1 text-xs': size === 'sm',
            'px-4 py-1.5 text-sm': size === 'md',
            'px-6 py-2.5 text-base': size === 'lg',
          }
        ),
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
};
