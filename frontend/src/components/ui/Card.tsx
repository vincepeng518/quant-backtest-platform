import React from 'react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  hoverEffect?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  className,
  hoverEffect = false,
  ...props
}) => {
  return (
    <div
      className={twMerge(
        clsx(
          'bg-surface p-6 select-none rounded-lg border border-border/20 shadow-[0_1px_3px_rgba(0,0,0,0.12)]',
          {
            'transition-all duration-150 ease-out hover:border-accent/40 hover:shadow-[0_4px_16px_rgba(0,0,0,0.18)]':
              hoverEffect,
          }
        ),
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
};
