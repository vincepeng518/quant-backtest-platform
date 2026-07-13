'use client';

import { create } from 'zustand';

export type ToastKind = 'success' | 'danger' | 'info';

export interface ToastItem {
  id: string;
  title: string;
  message?: string;
  kind: ToastKind;
}

interface ToastStore {
  toasts: ToastItem[];
  push: (t: { title: string; message?: string; kind?: ToastKind }) => void;
  dismiss: (id: string) => void;
}

export const useToastStore = create<ToastStore>((set, get) => ({
  toasts: [],
  push: ({ title, message, kind = 'info' }) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const item: ToastItem = { id, title, message, kind };
    const next = [...get().toasts, item].slice(-3);
    set({ toasts: next });
    setTimeout(() => get().dismiss(id), 5000);
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}));
