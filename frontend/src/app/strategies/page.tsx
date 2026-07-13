'use client';

import React, { useEffect, useState, useCallback } from 'react';
import api from '@/lib/api';
import { UserStrategy, StrategyPayload } from '@/types/api';
import { Card } from '@/components/ui/Card';
import { PageShell } from '@/components/layout/PageShell';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';

const EMPTY_FORM: StrategyPayload = {
  name: '',
  description: '',
  category: '',
  code: '',
};

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<UserStrategy[]>([]);
  const [form, setForm] = useState<StrategyPayload>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStrategies = useCallback(async () => {
    try {
      const data = await api.listUserStrategies();
      setStrategies(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load strategies');
    }
  }, []);

  useEffect(() => {
    loadStrategies();
  }, [loadStrategies]);

  const handleChange = (
    field: keyof StrategyPayload,
    value: string
  ) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const resetForm = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (editingId) {
        await api.updateStrategy(editingId, form);
      } else {
        await api.uploadStrategy(form);
      }
      resetForm();
      await loadStrategies();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save strategy');
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = async (id: string) => {
    setError(null);
    try {
      const strategy = await api.getUserStrategy(id);
      setForm({
        name: strategy.name,
        description: strategy.description,
        category: strategy.category,
        code: strategy.code,
      });
      setEditingId(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load strategy');
    }
  };

  const handleDelete = async (id: string) => {
    setError(null);
    try {
      await api.deleteStrategy(id);
      if (editingId === id) {
        resetForm();
      }
      await loadStrategies();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete strategy');
    }
  };

  return (
    <PageShell
      eyebrow="Strategies / library"
      title="策略庫"
      subtitle="上傳、編輯並管理你的自定義 Python 策略。持久化進版本庫，跨裝置與重啟皆存活。"
    >
      {/* Form */}
      <Card>
        <h2 className="mb-6 text-sm font-semibold uppercase tracking-wider text-textSecondary">
          {editingId ? 'Edit Strategy' : 'New Strategy'}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <Input
              label="Name"
              value={form.name}
              onChange={(e) => handleChange('name', e.target.value)}
              placeholder="My Strategy"
            />
            <Input
              label="Category"
              value={form.category}
              onChange={(e) => handleChange('category', e.target.value)}
              placeholder="Momentum"
            />
          </div>

          <Input
            label="Description"
            value={form.description}
            onChange={(e) => handleChange('description', e.target.value)}
            placeholder="Short description of the strategy"
          />

          <div className="w-full">
            <label className="block text-xs font-medium text-textSecondary uppercase tracking-wider mb-2">
              Code
            </label>
            <textarea
              value={form.code}
              onChange={(e) => handleChange('code', e.target.value)}
              rows={10}
              placeholder="def signal(df): ..."
              className="w-full resize-y rounded-lg bg-transparent border border-border/10 p-3 font-mono text-sm text-text focus:border-accent focus:outline-none duration-150 ease-out"
            />
          </div>

          {error && <p className="text-sm font-mono text-danger">{error}</p>}

          <div className="flex items-center gap-3 border-t border-border/10 pt-4">
            <Button type="submit" variant="primary" disabled={loading}>
              {loading
                ? 'Saving...'
                : editingId
                ? 'Update Strategy'
                : 'Upload Strategy'}
            </Button>
            {editingId && (
              <Button type="button" variant="ghost" onClick={resetForm}>
                Cancel
              </Button>
            )}
          </div>
        </form>
      </Card>

      {/* Library list */}
      <div className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-textSecondary">
          Your Strategies
        </h2>

        {strategies.length === 0 ? (
          <Card>
            <p className="text-sm text-textSecondary">
              No strategies yet. Upload your first one above.
            </p>
          </Card>
        ) : (
          strategies.map((s) => (
            <Card key={s.id} hoverEffect>
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="truncate font-medium text-text">{s.name}</h3>
                    {s.category && (
                      <span className="rounded bg-surface px-2 py-0.5 font-mono text-xs text-textSecondary">
                        {s.category}
                      </span>
                    )}
                  </div>
                  {s.description && (
                    <p className="mt-1 truncate text-sm text-textSecondary">
                      {s.description}
                    </p>
                  )}
                  <p className="mt-2 font-mono text-xs text-textSecondary">
                    Updated {new Date(s.updated_at * 1000).toLocaleString()}
                  </p>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => handleEdit(s.id)}
                  >
                    Edit
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(s.id)}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            </Card>
          ))
        )}
      </div>
    </PageShell>
  );
};
