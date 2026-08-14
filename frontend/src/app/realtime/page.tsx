'use client';

import React, { useEffect, useRef, useState } from 'react';
import { PageShell } from '@/components/layout/PageShell';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';

const WS_URL = (typeof window !== 'undefined' && (window as any).__NEXT_DATA__?.runtimeConfig?.REALTIME_WS) || '';
const FALLBACK = 'wss://affectionate-alignment-production-6d7e.up.railway.app/api/ws/kline';

interface KlineMsg { type: string; symbol?: string; close?: string; ts?: number; latency_ms?: number; connected?: boolean; matches_total?: number; status?: string; message?: string; }

export default function RealtimePage() {
  const [conn, setConn] = useState<'idle' | 'connecting' | 'open' | 'error' | 'closed'>('idle');
  const [lastKline, setLastKline] = useState<KlineMsg | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [count, setCount] = useState(0);
  const [connected, setConnected] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [symbol, setSymbol] = useState('BTC-USDT');
  const [stop, setStop] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const stopRef = useRef(stop);
  stopRef.current = stop;

  useEffect(() => {
    return () => { try { wsRef.current?.close(); } catch {} };
  }, []);

  const start = () => {
    setConn('connecting'); setErr(null); setCount(0); setLastKline(null);
    const url = `${WS_URL || FALLBACK}`;
    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = () => {
        setConn('open');
        ws.send(JSON.stringify({ symbol, timeframe: '1m' }));
      };
      ws.onmessage = (ev) => {
        try {
          const data: KlineMsg = JSON.parse(ev.data);
          if (data.type === 'kline') {
            setLastKline(data);
            setLatency(data.latency_ms ?? null);
            setConnected(!!data.connected);
            setCount((c) => c + 1);
          } else if (data.type === 'status') {
            setConn(data.status === 'subscribing' ? 'open' : conn);
          } else if (data.type === 'error') {
            setErr(data.message ?? 'WebSocket 錯誤'); setConn('error');
          }
        } catch { /* binary/heartbeat */ }
      };
      ws.onclose = () => { if (!stopRef.current) { setConn('closed'); setConnected(false); } };
      ws.onerror = () => { setErr('WebSocket 連線失敗(檢查後端可用性)'); setConn('error'); };
    } catch (e: any) {
      setErr(String(e?.message ?? e)); setConn('error');
    }
  };

  const halt = () => { setStop(true); try { wsRef.current?.close(); } catch {} setConn('closed'); setConnected(false); };

  return (
    <PageShell eyebrow="Realtime / BingX WS" title="實時 K 線與模擬撮合" subtitle="BingX WebSocket 實時 K 線 → 模擬掛單履約延遲(<0.2s 目標)。">
      <Card className="p-5 space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs font-mono text-textSecondary space-y-1">
            標的
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className="w-40 bg-background border border-border/10 rounded-md px-2 py-1.5 text-sm text-text">
              {['BTC-USDT', 'ETH-USDT', 'SOL-USDT'].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          {conn !== 'open' ? (
            <Button onClick={start}>開始實時</Button>
          ) : (
            <Button variant="ghost" onClick={halt}>停止</Button>
          )}
          <span className={`ml-auto text-xs font-mono rounded px-2 py-1 ${connected ? 'bg-success/15 text-success' : 'bg-surface text-textSecondary'}`}>
            {connected ? '● 已連線' : conn === 'open' ? '○ 訂閱中' : conn}
          </span>
        </div>

        {err && <p className="text-xs font-mono text-danger break-all">{err}</p>}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Metric label="最新 Close" value={lastKline?.close ?? '—'} />
          <Metric label="模擬撮合延遲" value={latency != null ? `${latency.toFixed(4)}ms` : '—'} />
          <Metric label="收到 kline" value={String(count)} />
          <Metric label="狀態" value={conn.toUpperCase()} />
        </div>

        <div className="text-[11px] font-mono text-textSecondary">
          {lastKline ? `最後更新: symbol=${lastKline.symbol} · ts=${lastKline.ts} · matches_total=${lastKline.matches_total}` : '等待實時 K 線…(若無推送,確認 BingX WS 連線)'}
        </div>
      </Card>
    </PageShell>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-surface p-3">
      <p className="text-[11px] font-mono text-textSecondary">{label}</p>
      <p className="mt-1 truncate font-mono text-sm text-text">{value}</p>
    </div>
  );
}
