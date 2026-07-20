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
          // TV-style surface: subtle border + soft shadow for depth hierarchy
          'bg-surface p-6 duration-150 ease-out select-none border border-border/10 shadow-[0_1px_3px_rgba(0,0,0,0.12)]',
          {
            'hover:border-accent/35 hover:shadow-[0_4px_16px_rgba(0,0,0,0.18)] transition-all': hoverEffect,
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
