'use client';

import React from 'react';

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const SIZES: Record<NonNullable<SpinnerProps['size']>, number> = {
  sm: 14,
  md: 20,
  lg: 32,
};

export const Spinner: React.FC<SpinnerProps> = ({ size = 'md', className = '' }) => {
  const px = SIZES[size];
  return (
    <svg
      className={`animate-spin text-accent ${className}`}
      width={px}
      height={px}
      viewBox="0 0 24 24"
      fill="none"
      role="status"
      aria-label="loading"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
};
