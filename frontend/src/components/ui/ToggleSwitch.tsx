'use client';

import React from 'react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

interface ToggleSwitchProps {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  label?: string;
  badge?: 'active' | 'off';
}

export const ToggleSwitch: React.FC<ToggleSwitchProps> = ({
  checked,
  onChange,
  disabled = false,
  label,
  badge,
}) => {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={twMerge(
          clsx(
            'relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 ease-out focus:outline-none focus:ring-1 focus:ring-accent/30',
            checked
              ? 'bg-accent shadow-[0_0_6px_rgba(56,189,248,0.3)]'
              : 'bg-surface2/60 border border-white/[0.08]',
            disabled && 'opacity-40 cursor-not-allowed'
          )
        )}
      >
        <span
          className={twMerge(
            clsx(
              'inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow-sm transition-transform duration-200 ease-out',
              checked ? 'translate-x-[18px]' : 'translate-x-[2px]'
            )
          )}
        />
      </button>
      {label && (
        <span className="text-sm font-medium text-text select-none">{label}</span>
      )}
      {badge && (
        <span
          className={clsx(
            'text-[10px] font-mono font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border',
            badge === 'active'
              ? 'bg-success/10 text-success border-success/20'
              : 'bg-textSecondary/10 text-textSecondary/60 border-textSecondary/10'
          )}
        >
          {badge === 'active' ? 'ACTIVE' : 'OFF'}
        </span>
      )}
    </div>
  );
};
