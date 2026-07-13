import React from 'react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizeMap: Record<NonNullable<SpinnerProps['size']>, string> = {
  sm: 'h-4 w-4 border-2',
  md: 'h-6 w-6 border-2',
  lg: 'h-8 w-8 border-[3px]',
};

export const Spinner: React.FC<SpinnerProps> = ({ size = 'md', className }) => {
  return (
    <span
      role="status"
      aria-label="loading"
      className={twMerge(
        clsx(
          'inline-block animate-spin rounded-full border-current border-t-transparent text-accent',
          sizeMap[size]
        ),
        className
      )}
    />
  );
};
