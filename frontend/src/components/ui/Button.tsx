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
          'inline-flex items-center justify-center font-medium transition-all duration-150 ease-out focus:outline-none disabled:opacity-50 disabled:pointer-events-none active:scale-[0.97]',
          {
            'bg-accent text-accentInk hover:bg-accentStrong': variant === 'primary',
            'bg-surface2 text-text hover:bg-surface2/70': variant === 'secondary',
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
    />
  );
};
