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
          // No borders, no shadows, precise typography grid bounding
          'bg-surface p-6 duration-150 ease-out select-none border-t border-border/10',
          {
            'hover:border-accent/35 transition-all': hoverEffect,
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
