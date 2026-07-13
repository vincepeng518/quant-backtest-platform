'use client';

import React from 'react';
import { useToastStore, ToastKind } from '@/stores/useToastStore';

const KIND_STYLE: Record<ToastKind, string> = {
  success: 'border-l-accent text-accent',
  danger: 'border-l-danger text-danger',
  info: 'border-l-textSecondary text-textSecondary',
};

export const ToastViewport: React.FC = () => {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-80 max-w-[calc(100vw-2rem)]">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`bg-surface border border-border/10 border-l-2 ${KIND_STYLE[t.kind]} rounded-md px-4 py-3 shadow-lg backdrop-blur-sm`}
          role="status"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex flex-col">
              <span className="text-sm font-semibold text-text">{t.title}</span>
              {t.message && <span className="text-xs text-textSecondary mt-0.5">{t.message}</span>}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              className="text-textSecondary hover:text-text transition-colors text-xs leading-none"
              aria-label="dismiss"
            >
              ✕
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};
