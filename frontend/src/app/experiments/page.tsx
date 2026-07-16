'use client';

import { useEffect, useState, useCallback } from 'react';
import api from '@/lib/api';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { Button } from '@/components/ui/Button';

interface Experiment {
  id: string;
  kind: string;
  label: string;
  created_at: number;
  config: any;
  metrics: Record<string, any>;
}

export default function ExperimentsPage() {
  const [exps, setExps] = useState<Experiment[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [compare, setCompare] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  // validate panel state
  const [valSym, setValSym] = useState('BTC/USDT');
  const [valName, setValName] = useState('sma');
  const [valPeriod, setValPeriod] = useState(14);
  const [valRefs, setValRefs] = useState('');
  const [valResult, setValResult] = useState<any>(null);
  const [valError, setValError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listExperiments();
      setExps(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggle = (id: string) => {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  };

  const runCompare = async () => {
    if (selected.length < 2) return;
    const data = await api.compareExperiments(selected);
    setCompare(data);
  };

  const runValidate = async () => {
    setValError(null);
    setValResult(null);
    try {
      const reference = valRefs.split(',').map((x) => parseFloat(x.trim())).filter((n) => !isNaN(n));
      if (reference.length === 0) { setValError('reference 需為逗號分隔數字'); return; }
      const r = await api.validateIndicator({
        symbol: valSym, timeframe: '1h', source: 'bingx',
        name: valName, period: valPeriod, reference,
      });
      setValResult(r);
    } catch (e: any) {
      setValError(e.message || '校驗失敗');
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-text">實驗紀錄 (Experiments)</h1>
      <p className="text-sm text-text-muted">
        每次回測 / 優化自動存檔，可橫向比較（借鑒 Qlib Recorder）。
      </p>

      <Card>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">紀錄列表</h2>
          <Button onClick={load} disabled={loading}>重新整理</Button>
        </div>
        {exps.length === 0 ? (
          <p className="text-sm text-text-muted">尚無紀錄，跑一次回測或優化即出現。</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-text-muted border-b border-grid">
                  <th className="p-2">選</th><th className="p-2">類型</th><th className="p-2">標籤</th>
                  <th className="p-2">時間</th><th className="p-2">關鍵指標</th>
                </tr>
              </thead>
              <tbody>
                {exps.map((e) => (
                  <tr key={e.id} className="border-b border-grid/50">
                    <td className="p-2"><input type="checkbox" checked={selected.includes(e.id)} onChange={() => toggle(e.id)} /></td>
                    <td className="p-2"><span className="px-2 py-0.5 rounded bg-grid text-xs">{e.kind}</span></td>
                    <td className="p-2 font-mono text-xs">{e.label}</td>
                    <td className="p-2 text-xs text-text-muted">{new Date(e.created_at * 1000).toLocaleString()}</td>
                    <td className="p-2 text-xs">{Object.entries(e.metrics).slice(0, 3).map(([k, v]) => `${k}=${typeof v === 'number' ? v.toFixed(2) : v}`).join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Button onClick={runCompare} disabled={selected.length < 2} className="mt-4">
          比較選中 ({selected.length})
        </Button>
      </Card>

      {compare && (
        <Card>
          <h2 className="text-lg font-semibold mb-4">比較結果</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-text-muted border-b border-grid">
                  <th className="p-2">指標</th>
                  {compare.experiments.map((e: any) => <th key={e.id} className="p-2">{e.label}</th>)}
                </tr>
              </thead>
              <tbody>
                {compare.metric_keys.map((k: string) => (
                  <tr key={k} className="border-b border-grid/50">
                    <td className="p-2 font-mono text-xs">{k}</td>
                    {compare.experiments.map((e: any) => (
                      <td key={e.id} className="p-2 text-xs">{JSON.stringify(e.metrics[k] ?? '-')}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card>
        <h2 className="text-lg font-semibold mb-4">指標校驗 (TV vs 引擎)</h2>
        <p className="text-sm text-text-muted mb-4">
          貼上外部參考值（如 TradingView 圖表讀數，逗號分隔），比對我們引擎自算指標。
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <TextInputL label="Symbol" value={valSym} onChange={setValSym} />
          <Select label="指標" value={valName} onChange={(e) => setValName(e.target.value)} options={[{label:'SMA',value:'sma'},{label:'EMA',value:'ema'},{label:'RSI',value:'rsi'}]} />
          <TextInputL label="週期" value={String(valPeriod)} onChange={(v) => setValPeriod(parseInt(v) || 14)} />
          <TextInputL label="參考值 (逗號分隔)" value={valRefs} onChange={setValRefs} />
        </div>
        <Button onClick={runValidate}>校驗</Button>
        {valError && <p className="mt-3 text-sm text-danger">{valError}</p>}
        {valResult && (
          <div className="mt-3 text-sm">
            <p className="font-mono">max_abs_error: {valResult.max_abs_error.toFixed(6)} | mean: {valResult.mean_abs_error.toFixed(6)}</p>
            <p className={valResult.matched ? 'text-up' : 'text-danger'}>
              {valResult.matched ? '✓ 完全吻合' : `✗ ${valResult.mismatches} 點偏差超 tolerance`}
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}

function TextInputL({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block">
      <span className="text-xs text-text-muted">{label}</span>
      <input
        className="mt-1 w-full rounded bg-bg border border-grid px-2 py-1 text-sm text-text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
