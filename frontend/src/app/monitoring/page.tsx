'use client';

import React, { useEffect, useState } from 'react';
import api from '@/lib/api';
import { Card } from '@/components/ui/Card';
import { PageShell } from '@/components/layout/PageShell';
import { MetricsCard } from '@/components/backtest/MetricsCard';
import { EmptyState } from '@/components/ui/EmptyState';
import { Spinner } from '@/components/ui/Spinner';

export default function MonitoringPage() {
  const [stats, setStats] = useState<any>(null);
  const [trades, setTrades] = useState<any[]>([]);
  const [rounds, setRounds] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, t, r] = await Promise.all([
        api.getMonitorStats(),
        api.getMonitorTrades(50),
        api.getMonitorRounds(50),
      ]);
      setStats(s);
      setTrades(t.trades || []);
      setRounds(r.rounds || []);
    } catch (e: any) {
      setError(e?.message || '監控數據載入失敗');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, []);

  if (loading) return <PageShell eyebrow="Monitor" title="predict.fun 監控"><Spinner /></PageShell>;
  if (error) return <PageShell eyebrow="Monitor" title="predict.fun 監控"><EmptyState title="錯誤" description={error} /></PageShell>;

  const d = stats?.data;
  const sh = d?.shadow || {};

  return (
    <PageShell
      eyebrow="Monitor / predict.fun"
      title="predict.fun 監控"
      subtitle="影子交易實時戰績與輪次明細。數據源：本機監控守護進程 (systemd predict-monitor.service)。"
    >
      <div className="flex items-center justify-between">
        <span className={`rounded-full px-3 py-1 text-xs font-mono ${stats?.available ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'}`}>
          {stats?.available ? `● LIVE · ${stats.updated_at?.slice(0, 19)}` : '● 離線'}
        </span>
        <button onClick={load} className="text-xs text-textSecondary hover:text-text">刷新</button>
      </div>

      {stats?.available ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <MetricsCard label="影子交易" value={String(sh.total ?? 0)} />
          <MetricsCard label="已結算" value={String(sh.resolved ?? 0)} />
          <MetricsCard label="勝率" value={`${(sh.win_rate ?? 0).toFixed(1)}%`} color={(sh.win_rate ?? 0) >= 50 ? 'positive' : 'negative'} />
          <MetricsCard label="累計 P&L" value={String(sh.total_pnl ?? 0)} color={(sh.total_pnl ?? 0) >= 0 ? 'positive' : 'negative'} />
        </div>
      ) : (
        <Card><EmptyState title="監控守護未連線" description="啟動 systemctl --user start predict-monitor.service" /></Card>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card className="p-0 overflow-hidden">
          <div className="flex items-center justify-between p-6 pb-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary">影子交易明細</h3>
            <span className="text-xs font-mono text-textSecondary">{trades.length} fills</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-mono">
              <thead>
                <tr className="text-left text-xs uppercase text-textSecondary border-t border-border/10">
                  <th className="px-6 py-3">#</th>
                  <th className="px-6 py-3">Round</th>
                  <th className="px-6 py-3">Side</th>
                  <th className="px-6 py-3 text-right">PnL</th>
                  <th className="px-6 py-3">Win</th>
                </tr>
              </thead>
              <tbody>
                {trades.length === 0 ? (
                  <tr><td colSpan={5} className="px-6 py-6 text-center text-textSecondary">尚無交易</td></tr>
                ) : trades.map((t, i) => (
                  <tr key={t.id || i} className="border-t border-border/10 hover:bg-white/[0.02]">
                    <td className="px-6 py-3 text-textSecondary">{i + 1}</td>
                    <td className="px-6 py-3 text-text">{t.round_id}</td>
                    <td className="px-6 py-3 text-text">{t.side}</td>
                    <td className={`px-6 py-3 text-right font-semibold ${Number(t.pnl) >= 0 ? 'text-success' : 'text-danger'}`}>{Number(t.pnl ?? 0).toFixed(2)}</td>
                    <td className="px-6 py-3 text-textSecondary">{t.win == null ? '—' : t.win ? '✓' : '✗'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="p-0 overflow-hidden">
          <div className="flex items-center justify-between p-6 pb-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-textSecondary">輪次日誌</h3>
            <span className="text-xs font-mono text-textSecondary">{rounds.length} rounds</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-mono">
              <thead>
                <tr className="text-left text-xs uppercase text-textSecondary border-t border-border/10">
                  <th className="px-6 py-3">Round</th>
                  <th className="px-6 py-3 text-right">Open</th>
                  <th className="px-6 py-3 text-right">Close</th>
                  <th className="px-6 py-3 text-right">Target</th>
                  <th className="px-6 py-3">Resolved</th>
                </tr>
              </thead>
              <tbody>
                {rounds.length === 0 ? (
                  <tr><td colSpan={5} className="px-6 py-6 text-center text-textSecondary">尚無輪次</td></tr>
                ) : rounds.map((r, i) => (
                  <tr key={r.id || i} className="border-t border-border/10 hover:bg-white/[0.02]">
                    <td className="px-6 py-3 text-text">{r.round_id}</td>
                    <td className="px-6 py-3 text-right text-text">{Number(r.open_price ?? 0).toFixed(2)}</td>
                    <td className="px-6 py-3 text-right text-text">{Number(r.close_price ?? 0).toFixed(2)}</td>
                    <td className="px-6 py-3 text-right text-textSecondary">{Number(r.target_price ?? 0).toFixed(2)}</td>
                    <td className={`px-6 py-3 ${r.resolved ? 'text-success' : 'text-textSecondary'}`}>{r.resolved ? '✓' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </PageShell>
  );
}
