'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';

/* ── types ── */
interface Msg {
  role: 'user' | 'assistant';
  content: string;
  ts: number;
}

/* ── quick prompts ── */
const QUICK = [
  { label: '策略健檢', text: '幫我檢查這個策略的邏輯是否有前視偏差\n\n[貼上你的策略代碼]' },
  { label: '回測解讀', text: 'Sharpe 1.8, PF 2.1, MaxDD -12%, 87 筆交易，這個策略能用嗎？' },
  { label: '參數優化', text: '我的策略有 fast_period 和 slow_period 兩個參數，怎麼設計 walk-forward 驗證？' },
  { label: '風控建議', text: '1萬本金，每筆固定倉位 10%，MaxDD 歷史 -15%，怎麼改善資金管理？' },
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

export default function ChatHome() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  /* ── auto-scroll ── */
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  /* ── textarea auto-resize ── */
  useEffect(() => {
    if (taRef.current) {
      taRef.current.style.height = 'auto';
      taRef.current.style.height = Math.min(taRef.current.scrollHeight, 200) + 'px';
    }
  }, [input]);

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || streaming) return;

    setError(null);
    const userMsg: Msg = { role: 'user', content: trimmed, ts: Date.now() };
    const assistantId = Date.now() + 1;
    setMessages((prev) => [...prev, userMsg, { role: 'assistant', content: '', ts: assistantId }]);
    setInput('');
    setStreaming(true);

    try {
      const res = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: [...messages, { role: 'user', content: trimmed }].map((m) => ({
            role: m.role,
            content: m.content,
          })),
        }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error('no stream body');

      const decoder = new TextDecoder();
      let buffer = '';
      let accumulated = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const chunk = line.slice(6);
          if (chunk === '[DONE]') {
            break;
          }
          try {
            const obj = JSON.parse(chunk);
            if (obj.error) {
              setError(obj.error);
              break;
            }
            if (obj.content) {
              accumulated += obj.content;
              setMessages((prev) =>
                prev.map((m) =>
                  m.ts === assistantId ? { ...m, content: accumulated } : m
                )
              );
            }
          } catch {
            // skip malformed
          }
        }
      }

      if (!accumulated && !error) {
        setMessages((prev) =>
          prev.map((m) =>
            m.ts === assistantId ? { ...m, content: '（無回覆內容）' } : m
          )
        );
      }
    } catch (e: any) {
      setError(e.message || '連線失敗');
      setMessages((prev) =>
        prev.filter((m) => m.ts !== assistantId)
      );
    } finally {
      setStreaming(false);
    }
  }, [messages, streaming, error]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  const clear = () => {
    setMessages([]);
    setError(null);
  };

  /* ── empty state ── */
  if (messages.length === 0) {
    return (
      <div className="mx-auto flex min-h-[calc(100vh-64px)] max-w-3xl flex-col px-4 pb-16 pt-12 md:px-6">
        {/* header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-textSecondary">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping bg-success opacity-60" />
              <span className="relative inline-flex h-1.5 w-1.5 bg-success" />
            </span>
            AI Assistant · online
          </div>
          <h1 className="mt-6 font-display text-3xl font-semibold leading-tight tracking-tight md:text-4xl">
            量化交易助手
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-textSecondary">
            策略設計、回測驗證、風險管理、代碼除錯。直接問。
          </p>
        </div>

        {/* quick prompts */}
        <div className="mb-6 grid gap-2 sm:grid-cols-2">
          {QUICK.map((q) => (
            <button
              key={q.label}
              onClick={() => send(q.text)}
              disabled={streaming}
              className="group rounded-lg border border-border/40 bg-surface p-4 text-left transition-colors hover:border-accent/40 disabled:opacity-40"
            >
              <div className="font-display text-sm font-semibold tracking-tight transition-colors group-hover:text-accent">
                {q.label}
              </div>
              <div className="mt-1.5 line-clamp-2 font-mono text-[11px] leading-relaxed text-textSecondary">
                {q.text.split('\n')[0]}
              </div>
            </button>
          ))}
        </div>

        {/* input */}
        <InputArea
          input={input}
          setInput={setInput}
          onKeyDown={onKeyDown}
          send={() => send(input)}
          streaming={streaming}
          taRef={taRef}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-64px)] max-w-3xl flex-col px-4 pb-4 pt-4 md:px-6">
      {/* messages */}
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto pb-4">
        {messages.map((m, i) => (
          <MessageBubble key={i} msg={m} streaming={streaming && i === messages.length - 1 && m.role === 'assistant'} />
        ))}
        {error && (
          <div className="rounded-lg border border-danger/30 bg-danger/5 px-4 py-3 font-mono text-xs text-danger">
            {error}
          </div>
        )}
      </div>

      {/* input */}
      <div className="shrink-0">
        <div className="mb-2 flex items-center justify-between">
          <button
            onClick={clear}
            className="font-mono text-[11px] uppercase tracking-wider text-textSecondary transition-colors hover:text-danger"
          >
            清空對話
          </button>
          <span className="font-mono text-[11px] text-textSecondary/50">
            Enter 發送 · Shift+Enter 換行
          </span>
        </div>
        <InputArea
          input={input}
          setInput={setInput}
          onKeyDown={onKeyDown}
          send={() => send(input)}
          streaming={streaming}
          taRef={taRef}
        />
      </div>
    </div>
  );
}

/* ── message bubble ── */
function MessageBubble({ msg, streaming }: { msg: Msg; streaming?: boolean }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-lg px-4 py-3 ${
          isUser
            ? 'bg-accent/10 border border-accent/20'
            : 'bg-surface border border-border/30'
        }`}
      >
        {!isUser && (
          <div className="mb-1.5 flex items-center gap-1.5">
            <span className="h-1 w-1 bg-accent" />
            <span className="font-mono text-[10px] uppercase tracking-wider text-textSecondary">
              AI
            </span>
          </div>
        )}
        <div
          className={`text-sm leading-relaxed ${
            isUser ? 'text-text' : 'text-text/95'
          } ${streaming && !msg.content ? 'animate-pulse' : ''}`}
        >
          {msg.content || (streaming ? '思考中…' : '')}
        </div>
        <div className="mt-1.5 font-mono text-[10px] text-textSecondary/40">
          {new Date(msg.ts).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  );
}

/* ── input area ── */
function InputArea({
  input,
  setInput,
  onKeyDown,
  send,
  streaming,
  taRef,
}: {
  input: string;
  setInput: (s: string) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  send: () => void;
  streaming: boolean;
  taRef: React.RefObject<HTMLTextAreaElement>;
}) {
  return (
    <div className="relative rounded-xl border border-border/40 bg-surface focus-within:border-accent/50 transition-colors">
      <textarea
        ref={taRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={streaming}
        rows={1}
        placeholder="問任何量化交易問題…"
        className="w-full resize-none bg-transparent px-4 py-3 text-sm text-text placeholder:text-textSecondary/50 focus:outline-none disabled:opacity-50"
        style={{ minHeight: '48px' }}
      />
      <button
        onClick={send}
        disabled={streaming || !input.trim()}
        className="absolute bottom-3 right-3 flex h-7 w-7 items-center justify-center rounded-md bg-accent text-accentInk transition-colors hover:bg-accentStrong disabled:opacity-30 disabled:cursor-not-allowed"
        aria-label="發送"
      >
        {streaming ? (
          <span className="h-3 w-3 animate-spin rounded-full border-2 border-accentInk/30 border-t-accentInk" />
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        )}
      </button>
    </div>
  );
}
