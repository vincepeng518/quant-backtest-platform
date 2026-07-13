'use client';

import React, { useEffect, useState } from 'react';
import { PageShell } from '@/components/layout/PageShell';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { PriceChart } from '@/components/charts/PriceChart';
import { api } from '@/lib/api';

const TIMEFRAMES = ['15m', '1h', '4h', '1d'];

export default function DataPage() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [ohlcv, setOhlcv] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getSymbols().then((s) => setSymbols(s.map((x: any) => x.symbol))).catch(() => setSymbols([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.getOHLCV(symbol, timeframe)
      .then((d) => { if (!cancelled) setOhlcv(d); })
      .catch((e) => { if (!cancelled) setError(e?.message ?? 'failed to load'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol, timeframe]);

  return (
    <PageShell
      eyebrow="Data / market"
      title="市場數據預覽"
      subtitle="瀏覽可用交易對的歷史 K 線，確認數據源與時間框架後再投入回測。"
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Select
          label="Symbol"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          options={symbols.length ? symbols.map((s) => ({ label: s, value: s })) : [{ label: 'BTC/USDT', value: 'BTC/USDT' }]}
        />
        <Select
          label="Timeframe"
          value={timeframe}
          onChange={(e) => setTimeframe(e.target.value)}
          options={TIMEFRAMES.map((t) => ({ label: t, value: t }))}
        />
      </div>

      <Card className="min-h-[480px] flex items-center justify-center">
        {loading ? (
          <Spinner size="lg" />
        ) : error ? (
          <p className="text-sm font-mono text-danger">{error}</p>
        ) : ohlcv && ohlcv.length > 0 ? (
          <PriceChart data={ohlcv} />
        ) : (
          <EmptyState title="No data for this symbol/timeframe" description="Try another symbol or timeframe." />
        )}
      </Card>
    </PageShell>
  );
}
