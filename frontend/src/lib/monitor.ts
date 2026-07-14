'use client';

import { useEffect, useState } from 'react';
import { api } from './api';
import type { MonitorStats } from '@/types/api';

export function useMonitor() {
  const [stats, setStats] = useState<MonitorStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .getMonitorStats()
      .then((data: MonitorStats) => {
        if (!alive) return;
        setStats(data);
        setLoading(false);
      })
      .catch((e) => {
        if (!alive) return;
        setError(String(e?.message ?? e));
        setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  return { stats, loading, error };
}
