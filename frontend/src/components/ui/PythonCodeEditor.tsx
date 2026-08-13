'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { checkPythonSyntax, PySyntaxDiagnostic } from '@/lib/pythonSyntax';

/**
 * PythonCodeEditor — 輕量 Python 語法高亮 + 即時語法檢查的 textarea 編輯器。
 *
 * 設計：視覺高亮走「疊底 <pre> + 透明 <textarea>」；實際編輯仍由 <textarea>
 * 的 value/onChange 負責，因此外層只要照樣傳 value + onChange 即可，完全不改變
 * 既有 form.code 與提交路徑。
 *
 * Props：
 *   value      — 受控值（等於原本 form.code）
 *   onChange   — (text: string) => void（等於原本 e => setForm(...)）
 *   heightCls  — Tailwind 高度 class，預設 'h-72'（與原 textarea 一致）
 *   className  — 額外 class（保留 bg/邊框等，預設帶原 textarea 外觀）
 */
interface Props {
  value: string;
  onChange: (text: string) => void;
  heightCls?: string;
  className?: string;
  /** 測速注入：外部驗證工具可 call，回傳當下診斷與耗時。 */
  onValidate?: (r: { ok: boolean; diags: PySyntaxDiagnostic[]; elapsedMs: number }) => void;
}

/* ------------------------------------------------------------------ *
 * Python token 色彩（單一來源，高亮用）                              *
 * ------------------------------------------------------------------ */

// 簡單 Python lexer：回傳 [ [from, to, className], ... ]，純色段
const KW = new Set([
  'False','None','True','and','as','assert','async','await','break','class',
  'continue','def','del','elif','else','except','finally','for','from','global',
  'if','import','in','is','lambda','nonlocal','not','or','pass','raise','return',
  'try','while','with','yield',
]);
const BUILTINS = new Set(['print','len','range','str','int','float','list','dict','set','tuple','sum','min','max','abs','round','super','isinstance','hasattr','enumerate','zip','map','filter' ]);

type Seg = { from: number; to: number; cls: string };

function tokenizePython(src: string): Seg[] {
  const segs: Seg[] = [];
  const RE =
    /\s+|#[^\n]*|"""[\s\S]*?"""|'''[\s\S]*?'''|[uUbBfFrR]?[rR]?"(?:[^"\\]|\\.)*"|[uUbBfFrR]?[rR]?'(?:[^'\\]|\\.)*'|\b(?:0[xXoObB][0-9a-fA-F_]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\.\d+)\b|[A-Za-z_]\w*|==|!=|<=|>=|=>|\*\*|\/\/|<<|>>|[-+*/%=<>!&|^~.:,()\[\]{}@]+/g;
  let m: RegExpExecArray | null;
  let prevCls: string | null = null;
  while ((m = RE.exec(src)) !== null) {
    const tok = m[0];
    const start = m.index;
    const cls = classify(tok, prevCls);
    if (cls) segs.push({ from: start, to: start + tok.length, cls });
    prevCls = cls;
  }
  return segs;

  function classify(tok: string, prev: string | null): string {
    const first = tok[0];
    if (first === '#') return 'text-slate-500 italic';
    if (first === ' ' || first === '\t' || first === '\n') return '';
    if (KW.has(tok)) return 'text-fuchsia-500 font-semibold';
    if (BUILTINS.has(tok) && !prev) return 'text-sky-400';
    if (tok[0] === '"' || tok[0] === "'") return 'text-emerald-500';
    if (/^[0-9]|^\.\d/.test(tok)) return 'text-amber-400';
    if (tok === 'def' || tok === 'class') return 'text-fuchsia-500 font-semibold';
    if (/^[a-zA-Z_]\w*$/.test(tok)) return 'text-slate-100';
    if (/^[-+*/%=<>!&|^~@:,()\[\]{}]+$/.test(tok)) return 'text-orange-300/80';
    return '';
  }
}

/* ------------------------------------------------------------------ *
 * 組件                                                               *
 * ------------------------------------------------------------------ */

export default function PythonCodeEditor({ value, onChange, heightCls = 'h-72', className = '', onValidate }: Props) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const preRef = useRef<HTMLPreElement>(null);
  const [diags, setDiags] = useState<PySyntaxDiagnostic[]>([]);
  const [checked, setChecked] = useState(false);
  const [debounce, setDebounce] = useState(false);

  const segs = useMemo(() => tokenizePython(value), [value]);

  // 高亮 HTML：把 code 依 seg 分段包上 span
  const html = useMemo(() => {
    if (!segs.length) return escapeHtml(value);
    let out = '';
    let prev = 0;
    for (const s of segs) {
      out += escapeHtml(value.slice(prev, s.from));
      out += `<span class="${s.cls}">${escapeHtml(value.slice(s.from, s.to))}</span>`;
      prev = s.to;
    }
    out += escapeHtml(value.slice(prev));
    return out;
  }, [segs, value]);

  // 即時檢查：debounce 300ms
  useEffect(() => {
    if (!value) { setDiags([]); setChecked(false); setDebounce(false); return; }
    setDebounce(true);
    const id = window.setTimeout(() => {
      const r = checkPythonSyntax(value);
      setDiags(r.diagnostics);
      setChecked(true);
      setDebounce(false);
      onValidate?.({ ok: r.ok, diags: r.diagnostics, elapsedMs: r.elapsedMs });
    }, 300);
    return () => window.clearTimeout(id);
  }, [value, onValidate]);

  // 同步捲動：textarea scroll → pre scroll
  const syncScroll = useCallback((el: HTMLTextAreaElement) => {
    if (preRef.current) {
      preRef.current.scrollTop = el.scrollTop;
      preRef.current.scrollLeft = el.scrollLeft;
    }
  }, []);

  const errorLines = new Set(diags.map((d) => d.line));
  const hasError = diags.some((d) => d.severity === 'error');

  const base = className || 'w-full bg-background border border-border/10 rounded-md px-3 py-2 text-xs font-mono';

  return (
    <div>
      <div className={`relative ${heightCls} w-full bg-background border rounded-md font-mono text-xs leading-relaxed overflow-hidden ${hasError ? 'border-danger/40' : 'border-border/10'}`}>
        {/* 疊底高亮 */}
        <pre
          ref={preRef}
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 m-0 p-[9px] whitespace-pre overflow-hidden text-text"
          dangerouslySetInnerHTML={{ __html: html + '\n' }}
        />
        {/* 透明輸入層 */}
        <textarea
          ref={taRef}
          value={value}
          spellCheck={false}
          onChange={(e) => { onChange(e.target.value); syncScroll(e.target); }}
          onScroll={(e) => syncScroll(e.currentTarget)}
          onKeyDown={(e) => { if (e.key === 'Tab') { e.preventDefault(); } }}
          className="relative z-10 block w-full h-full bg-transparent text-transparent caret-sky-400 resize-none outline-none p-[9px] whitespace-pre overflow-auto"
          aria-label="Python 策略代碼編輯器"
        />
      </div>

      {/* 狀態列 + 錯誤列 */}
      <div className="mt-1 flex items-center gap-2 text-[11px]">
        {debounce ? (
          <span className="text-textSecondary">檢查中…</span>
        ) : hasError ? (
          <span className="text-danger font-medium">● {diags.filter((d) => d.severity === 'error').length} 個語法錯誤</span>
        ) : (
          <span className="text-success/80">● 語法正確</span>
        )}
        {errorLines.size > 0 && (
          <span className="text-textSecondary">行 {Array.from(errorLines).sort((a, b) => a - b).join(', ')}</span>
        )}
      </div>
      {diags.length > 0 && (
        <ul className="mt-1 space-y-1">
          {diags.slice(0, 6).map((d, idx) => (
            <li key={idx} className="font-mono text-[11px] text-danger bg-danger/5 border border-danger/10 rounded px-2 py-1">
              <span className="text-textSecondary mr-1">第 {d.line} 行</span>
              {d.message}
            </li>
          ))}
          {diags.length > 6 && (
            <li className="text-[11px] text-textSecondary">…其餘 {diags.length - 6} 條</li>
          )}
        </ul>
      )}
    </div>
  );
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
