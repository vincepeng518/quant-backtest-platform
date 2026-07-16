'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { useToastStore } from '@/stores/useToastStore';

interface UserMeta {
  id: string;
  name: string;
  description: string;
  category: string;
  filename?: string;
  created_at?: string;
  status?: string;
  error?: string | null;
  params_space?: Record<string, unknown>;
}

const SAMPLE = `from __future__ import annotations
from typing import Any, Optional

from strategies.base import Bar, Signal, StrategyBase


class MyStrategy(StrategyBase):
    description = "My custom strategy"
    category = "custom"

    def get_params_space(self):
        return {"fast_period": (5, 50, 1), "slow_period": (20, 200, 1)}

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.fast_period = int(params.get("fast_period", 20))
        self.slow_period = int(params.get("slow_period", 50))
        self.prices: list[float] = []
        self._pos = 0

    def next(self, bar: Bar) -> Optional[Signal]:
        self.prices.append(bar.close)
        if len(self.prices) < self.slow_period:
            return None
        fast_ma = sum(self.prices[-self.fast_period :]) / self.fast_period
        slow_ma = sum(self.prices[-self.slow_period :]) / self.slow_period
        prev_fast = sum(self.prices[-self.fast_period - 1 : -1]) / self.fast_period
        prev_slow = sum(self.prices[-self.slow_period - 1 : -1]) / self.slow_period
        golden = prev_fast <= prev_slow and fast_ma > slow_ma
        death = prev_fast >= prev_slow and fast_ma < slow_ma
        if golden and self._pos <= 0:
            self._pos = 1
            return Signal(action="buy", price=bar.close)
        if death and self._pos >= 0:
            self._pos = -1
            return Signal(action="sell", price=bar.close)
        return None
`;

export default function StrategiesPage() {
  const [templates, setTemplates] = useState<any[]>([]);
  const [user, setUser] = useState<UserMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [showUpload, setShowUpload] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', code: SAMPLE });
  const push = useToastStore((s) => s.push);
  const router = useRouter();

  const load = () => {
    Promise.all([api.getTemplates(), api.listUserStrategies()])
      .then(([t, u]) => {
        setTemplates(t as any[]);
        setUser(u as unknown as UserMeta[]);
        setLoading(false);
      })
      .catch((e) => {
        push({ kind: 'danger', title: '載入失敗', message: String(e?.message ?? e) });
        setLoading(false);
      });
  };

  useEffect(load, []);

  const submit = async () => {
    if (!form.name.trim() || !form.code.trim()) {
      push({ kind: 'danger', title: '請填寫名稱與代碼' });
      return;
    }
    try {
      const res: any = await api.uploadStrategy({ name: form.name, description: form.description, category: 'custom', code: form.code });
      push({ kind: 'success', title: '策略已上傳', message: form.name });
      if (res && Array.isArray(res.lookahead_warnings) && res.lookahead_warnings.length) {
        push({
          kind: 'danger',
          title: '⚠ 未來函數警告',
          message: `${res.lookahead_warnings.length} 處疑似使用未來數據，回測可能失真`,
        });
      }
      setShowUpload(false);
      setForm({ name: '', description: '', code: SAMPLE });
      load();
    } catch (e: any) {
      push({ kind: 'danger', title: '上傳失敗', message: e?.message ?? String(e) });
    }
  };

  const remove = async (id: string) => {
    try {
      await api.deleteStrategy(id);
      push({ kind: 'success', title: '已刪除策略' });
      load();
    } catch (e: any) {
      push({ kind: 'danger', title: '刪除失敗', message: e?.message ?? String(e) });
    }
  };

  if (loading) return <Spinner />;

  return (
    <div className="space-y-12 pb-12">
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-text">內建策略模板</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {templates.map((t) => (
            <div key={t.id} className="bg-surface border border-border/10 rounded-lg p-5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-text">{t.name}</span>
                <span className="text-xs text-textSecondary uppercase">{t.category}</span>
              </div>
              <p className="text-sm text-textSecondary">{t.description}</p>
              <span className="text-xs font-mono text-accent">{t.params?.length ?? 0} params</span>
            </div>
          ))}
          {templates.length === 0 && <EmptyState title="無內建模板" />}
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-text">我的策略</h2>
          <button onClick={() => setShowUpload(true)} className="text-sm text-accent hover:underline">+ 上傳策略</button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {user.map((s) => (
            <div key={s.id} className="bg-surface border border-border/10 rounded-lg p-5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-text">{s.name}</span>
                <span className={`text-xs ${s.status === 'error' ? 'text-danger' : 'text-success'}`}>{s.status ?? 'registered'}</span>
              </div>
              <p className="text-sm text-textSecondary">{s.description || s.filename}</p>
              {s.error && <p className="text-xs text-danger font-mono">{s.error}</p>}
              <div className="flex items-center gap-3 pt-1">
                <button onClick={() => router.push(`/backtest?strategy=user_${s.id}`)} className="text-xs text-accent hover:underline transition-colors">跑回測</button>
                <button onClick={() => router.push(`/optimize?strategy=user_${s.id}`)} className="text-xs text-accent hover:underline transition-colors">跑優化</button>
                <button onClick={() => remove(s.id)} className="text-xs text-textSecondary hover:text-danger transition-colors">刪除</button>
              </div>
            </div>
          ))}
          {user.length === 0 && <EmptyState title="尚無上傳策略" description="點擊右上角上傳你的 Python 策略" />}
        </div>
      </section>

      {showUpload && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setShowUpload(false)}>
          <div className="w-full max-w-2xl bg-surface border border-border/10 rounded-xl p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-semibold text-text">上傳策略</h3>
            <input
              className="w-full bg-background border border-border/10 rounded-md px-3 py-2 text-sm text-text"
              placeholder="策略名稱"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <input
              className="w-full bg-background border border-border/10 rounded-md px-3 py-2 text-sm text-text"
              placeholder="描述（選填）"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
            <textarea
              className="w-full h-72 bg-background border border-border/10 rounded-md px-3 py-2 text-xs font-mono text-text"
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowUpload(false)} className="text-sm text-textSecondary px-4 py-2">取消</button>
              <button onClick={submit} className="text-sm text-accent border border-accent/30 rounded-md px-4 py-2 hover:bg-accent/10 transition-colors">上傳</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
