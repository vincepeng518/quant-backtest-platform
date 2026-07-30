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
          'bg-surface/90 backdrop-blur-md p-6 select-none rounded-xl border border-white/[0.08] shadow-card transition-all duration-200',
          {
            'hover:shadow-card-hover hover:-translate-y-[1px]':
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
