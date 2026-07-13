import React from 'react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

interface EmptyStateProps {
  title: string;
  description?: string;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  className,
}) => {
  return (
    <div
      className={twMerge(
        clsx(
          'flex flex-col items-center justify-center gap-2 py-12 text-center'
        ),
        className
      )}
    >
      <p className="text-sm font-medium text-text">{title}</p>
      {description ? (
        <p className="text-xs text-textSecondary font-mono">{description}</p>
      ) : null}
    </div>
  );
};
