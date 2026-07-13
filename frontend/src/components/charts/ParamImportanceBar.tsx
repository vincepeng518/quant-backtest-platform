'use client';

import React from 'react';

interface Trial {
  params: Record<string, any>;
  score: number;
}

interface Props {
  trials: Trial[];
}

export const ParamImportanceBar: React.FC<Props> = ({ trials }) => {
  if (!trials.length) return null;
  const keys = Object.keys(trials[0].params);
  const agg: Record<string, { sum: number; n: number }> = {};
  for (const t of trials) {
    for (const k of keys) {
      agg[k] = agg[k] || { sum: 0, n: 0 };
      agg[k].sum += t.score;
      agg[k].n += 1;
    }
  }
  const rows = keys.map((k) => ({ k, avg: agg[k].n ? agg[k].sum / agg[k].n : 0 }));
  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
  return (
    <div className="space-y-3">
      {rows.map((r) => {
        const pct = (Math.abs(r.avg) / maxAbs) * 100;
        const pos = r.avg >= 0;
        return (
          <div key={r.k} className="space-y-1">
            <div className="flex justify-between text-xs font-mono text-textSecondary">
              <span>{r.k}</span>
              <span className={pos ? 'text-success' : 'text-danger'}>{r.avg.toFixed(3)}</span>
            </div>
            <div className="h-2 rounded-full bg-surface overflow-hidden">
              <div
                className={`h-full rounded-full ${pos ? 'bg-success' : 'bg-danger'}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
};
