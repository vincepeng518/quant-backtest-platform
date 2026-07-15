'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { PageShell } from '@/components/layout/PageShell';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { api } from '@/lib/api';
import {
  AdminOverview,
  MonitoredSymbol,
  CredentialStatus,
  TaskHistoryItem,
  UsageStat,
  SiteConfig,
  SiteConfigUpdate,
} from '@/types/api';
import {
  Star,
  Plus,
  Trash2,
  KeyRound,
  History as HistoryIcon,
  BarChart3,
  Settings2,
  ShieldCheck,
  ShieldAlert,
} from 'lucide-react';

const fmtInt = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 0 });

export default function AdminPage() {
  const router = useRouter();
  const [data, setData] = useState<AdminOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .getAdminOverview()
      .then(setData)
      .catch((e) => setError(e?.message ?? 'failed to load admin panel'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <PageShell eyebrow="Admin / owner" title="站長管理面板">
        <Card className="flex justify-center py-16"><Spinner size="lg" /></Card>
      </PageShell>
    );
  }
  if (error || !data) {
    return (
      <PageShell eyebrow="Admin / owner" title="站長管理面板">
        <Card>
          <p className="text-sm font-mono text-danger p-6">{error ?? 'no data'}</p>
          <Button variant="secondary" onClick={load}>重試</Button>
        </Card>
      </PageShell>
    );
  }

  return (
    <PageShell
      eyebrow="Admin / owner"
      title="站長管理面板"
      subtitle="Solo SaaS 站長視角：監控標的、憑證狀態（不暴露明文）、任務歷史、站點配置與使用量統計。"
    >
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <WatchlistPanel items={data.watchlist} onChange={load} />
        <CredentialsPanel items={data.credentials} />
      </div>
      <UsagePanel usage={data.usage} />
      <TaskHistoryPanel items={data.task_history} onOpen={(id) => router.push(`/backtest?task=${id}`)} />
      <ConfigPanel
        config={data.config}
        saving={saving}
        saveMsg={saveMsg}
        onSave={async (patch) => {
          setSaving(true);
          setSaveMsg(null);
          try {
            await api.updateSiteConfig(patch);
            setSaveMsg('已儲存');
            load();
          } catch (e: any) {
            setSaveMsg(e?.message ?? '儲存失敗');
          } finally {
            setSaving(false);
            setTimeout(() => setSaveMsg(null), 2500);
          }
        }}
      />
    </PageShell>
  );
}

// ─────────────────────── 監控標的清單 ───────────────────────

const WatchlistPanel: React.FC<{ items: MonitoredSymbol[]; onChange: () => void }> = ({ items, onChange }) => {
  const [symbol, setSymbol] = useState('');
  const [market, setMarket] = useState('crypto');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const add = async () => {
    if (!symbol.trim()) return;
    setBusy(true); setErr(null);
    try {
      await api.addWatchlist({ symbol: symbol.trim(), market });
      setSymbol(''); onChange();
    } catch (e: any) { setErr(e?.message ?? 'add failed'); }
    finally { setBusy(false); }
  };
  const remove = async (s: string) => { await api.removeWatchlist(s).catch(() => {}); onChange(); };
  const pin = async (s: string) => { await api.toggleWatchlistPin(s).catch(() => {}); onChange(); };

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-textSecondary">監控標的清單</h2>
        <span className="font-mono text-xs text-textSecondary">{items.length} 檔</span>
      </div>
      <div className="mb-4 flex items-end gap-2">
        <Input label="新增標的" placeholder="ETH/USDT" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
        <Select label="市場" value={market} onChange={(e) => setMarket(e.target.value)} options={[
          { label: 'Crypto', value: 'crypto' },
          { label: 'TradFi', value: 'tradfi' },
          { label: 'Forex', value: 'forex' },
        ]} />
        <Button onClick={add} disabled={busy || !symbol.trim()} className="mb-1"><Plus className="mr-1 h-3.5 w-3.5" /> 加入</Button>
      </div>
      {err && <p className="mb-3 text-xs font-mono text-danger">{err}</p>}
      {items.length === 0 ? (
        <EmptyState title="空清單" description="加入要持續監控的標的，例如 BTC/USDT。" />
      ) : (
        <div className="max-h-72 overflow-y-auto divide-y divide-border/10 no-scrollbar">
          {items.map((it) => (
            <div key={it.symbol} className="flex items-center justify-between py-2.5 px-1">
              <div className="flex items-center gap-2">
                <button onClick={() => pin(it.symbol)} className="text-textSecondary hover:text-accent transition-colors" title={it.pinned ? '取消置頂' : '置頂'}>
                  <Star className={`h-4 w-4 ${it.pinned ? 'fill-accent text-accent' : ''}`} />
                </button>
                <div>
                  <p className="font-mono text-sm text-text">{it.symbol}</p>
                  <p className="text-[11px] text-textSecondary">{it.market}{it.exchange ? ` · ${it.exchange}` : ''}{it.description ? ` · ${it.description}` : ''}</p>
                </div>
              </div>
              <button onClick={() => remove(it.symbol)} className="text-textSecondary hover:text-danger transition-colors" title="移除">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
};

// ─────────────────────── 使用量統計 ───────────────────────

const USAGE_META: Record<string, { label: string }> = {
  total_runs: { label: '總任務數' },
  completed_runs: { label: '完成' },
  failed_runs: { label: '失敗' },
  total_trades: { label: '總交易筆數' },
  unique_symbols: { label: '監控標的數' },
  monitor_signals: { label: '監控訊號數' },
};

const UsagePanel: React.FC<{ usage: UsageStat[] }> = ({ usage }) => (
  <Card>
    <div className="mb-4 flex items-center justify-between">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-textSecondary">使用量統計</h2>
      <BarChart3 className="h-4 w-4 text-textSecondary" />
    </div>
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {usage.map((u) => {
        const meta = USAGE_META[u.metric] ?? { label: u.metric };
        return (
          <div key={u.metric} className="rounded-lg border border-border/10 bg-background/40 px-4 py-3">
            <p className="text-[11px] uppercase tracking-wider text-textSecondary">{meta.label}</p>
            <p className="mt-1 font-mono text-2xl font-semibold text-text">{fmtInt(u.value)}</p>
          </div>
        );
      })}
    </div>
  </Card>
);

// ─────────────────────── 任務歷史 ───────────────────────

const STATUS_STYLE: Record<string, string> = {
  completed: 'bg-success/10 text-success',
  error: 'bg-danger/10 text-danger',
  running: 'bg-accent/10 text-accent',
};

const TaskHistoryPanel: React.FC<{ items: TaskHistoryItem[]; onOpen: (id: string) => void }> = ({ items, onOpen }) => (
  <Card>
    <div className="mb-4 flex items-center justify-between">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-textSecondary">任務歷史（回測 / 優化 / 分析）</h2>
      <HistoryIcon className="h-4 w-4 text-textSecondary" />
    </div>
    {items.length === 0 ? (
      <EmptyState title="尚無任務記錄" description="執行回測後會在此顯示歷史。" />
    ) : (
      <div className="max-h-80 overflow-x-auto">
        <table className="w-full text-sm font-mono">
          <thead>
            <tr className="text-left text-xs uppercase text-textSecondary border-b border-border/10">
              <th className="px-3 py-2">任務 ID</th>
              <th className="px-3 py-2">類型</th>
              <th className="px-3 py-2">標的</th>
              <th className="px-3 py-2">週期</th>
              <th className="px-3 py-2">策略</th>
              <th className="px-3 py-2 text-right">Score</th>
              <th className="px-3 py-2">狀態</th>
              <th className="px-3 py-2">時間</th>
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.task_id} className="border-t border-border/10 hover:bg-white/[0.02] transition-colors cursor-pointer" onClick={() => onOpen(t.task_id)}>
                <td className="px-3 py-2 text-text">{t.task_id}</td>
                <td className="px-3 py-2 text-textSecondary">{t.kind}</td>
                <td className="px-3 py-2 text-text">{t.symbol ?? '—'}</td>
                <td className="px-3 py-2 text-textSecondary">{t.timeframe ?? '—'}</td>
                <td className="px-3 py-2 text-textSecondary">{t.strategy ?? '—'}</td>
                <td className="px-3 py-2 text-right text-text">{t.score != null ? t.score.toFixed(3) : '—'}</td>
                <td className="px-3 py-2">
                  <span className={`rounded px-2 py-0.5 text-[11px] ${STATUS_STYLE[t.status] ?? 'bg-border/20 text-textSecondary'}`}>{t.status}</span>
                </td>
                <td className="px-3 py-2 text-textSecondary">{t.created_at?.slice(0, 19)?.replace('T', ' ') ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </Card>
);

// ─────────────────────── 站點配置 ───────────────────────

const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'];

const ConfigPanel: React.FC<{
  config: SiteConfig;
  saving: boolean;
  saveMsg: string | null;
  onSave: (patch: Partial<SiteConfigUpdate>) => void;
}> = ({ config, saving, saveMsg, onSave }) => {
  const [tf, setTf] = useState(config.default_timeframe ?? '1h');
  const [ddGuard, setDdGuard] = useState<string>(String(config.risk_guard_max_drawdown_pct ?? 0));
  const [maint, setMaint] = useState<boolean>(Boolean(config.maintenance_mode));

  const save = () => {
    const patch: Partial<SiteConfigUpdate> = {
      default_timeframe: tf,
      risk_guard_max_drawdown_pct: Number(ddGuard) || 0,
      maintenance_mode: maint,
    };
    onSave(patch);
  };

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-textSecondary">站點配置</h2>
        <Settings2 className="h-4 w-4 text-textSecondary" />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Select
          label="預設週期"
          value={tf}
          onChange={(e) => setTf(e.target.value)}
          options={TIMEFRAMES.map((t) => ({ label: t, value: t }))}
        />
        <Input
          label="最大回撤防護 %"
          type="number"
          value={ddGuard}
          onChange={(e) => setDdGuard(e.target.value)}
        />
        <div className="flex flex-col justify-end pb-1">
          <label className="mb-1 flex items-center gap-2 text-sm text-text">
            <input type="checkbox" checked={maint} onChange={(e) => setMaint(e.target.checked)} />
            維護模式
          </label>
        </div>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <Button onClick={save} disabled={saving}>{saving ? '儲存中…' : '儲存配置'}</Button>
        {saveMsg && <span className="text-xs font-mono text-textSecondary">{saveMsg}</span>}
      </div>
    </Card>
  );
};

// ─────────────────────── 憑證狀態（不暴露明文） ───────────────────────

const CredentialsPanel: React.FC<{ items: CredentialStatus[] }> = ({ items }) => {
  const kindLabel: Record<string, string> = { exchange: '交易所憑證', data_source: '數據源', infra: '基礎設施' };
  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-textSecondary">憑證狀態</h2>
        <KeyRound className="h-4 w-4 text-textSecondary" />
      </div>
      <p className="mb-4 text-xs text-textSecondary">僅顯示是否已配置與遮罩預覽，<span className="font-mono text-text">永不</span>回傳明文密鑰。</p>
      <div className="divide-y divide-border/10">
        {items.map((c) => (
          <div key={c.name} className="flex items-center justify-between py-2.5 px-1">
            <div>
              <p className="text-sm text-text">{c.name}</p>
              <p className="text-[11px] text-textSecondary">{kindLabel[c.kind] ?? c.kind}</p>
            </div>
            <div className="flex items-center gap-2">
              {c.configured ? (
                <>
                  <span className="font-mono text-xs text-textSecondary">{c.masked_value || '已設置'}</span>
                  <span className="flex items-center gap-1 rounded bg-success/10 px-2 py-0.5 text-[11px] text-success"><ShieldCheck className="h-3 w-3" /> 已配置</span>
                </>
              ) : (
                <span className="flex items-center gap-1 rounded bg-border/20 px-2 py-0.5 text-[11px] text-textSecondary"><ShieldAlert className="h-3 w-3" /> 未設置</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};