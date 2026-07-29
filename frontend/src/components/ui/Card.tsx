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
          'bg-surface/90 backdrop-blur-md p-6 select-none rounded-xl border border-white/[0.08] shadow-[0_4px_20px_rgba(0,0,0,0.3)] transition-all duration-200',
          {
            'hover:border-accent/40 hover:shadow-[0_6px_24px_rgba(56,189,248,0.15)] hover:-translate-y-[1px]':
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
