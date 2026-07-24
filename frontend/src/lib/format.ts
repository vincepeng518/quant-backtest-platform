/** Ink & Bullion palette — semantic data colors + surface tokens. */

export const TV_UP = '#089981';
export const TV_DOWN = '#f23645';
export const TV_NEUTRAL = '#808694';
export const TV_STRATEGY = '#c9a962';
export const TV_BH = '#808694';
export const TV_BG = '#0d111a';
export const TV_SURFACE = '#121722';
export const TV_BORDER = '#2c3446';
export const TV_TEXT = '#d8dce4';

/** Light-mode counterparts (for theme-aware chart components). */
export const IB_LIGHT = {
  bg: '#faf9f6',
  surface: '#ffffff',
  border: '#dedad0',
  text: '#141820',
  textSecondary: '#606674',
  accent: '#9a7b33',
};

export const IB_DARK = {
  bg: '#0d111a',
  surface: '#121722',
  border: '#2c3446',
  text: '#d8dce4',
  textSecondary: '#808694',
  accent: '#c9a962',
};

/** Safe Numeric: Infinity/null → '∞' / '—'; adds thousands seps + dynamic digits. */
export const safeFmt = (n: number | null | undefined, decimals = 2): string => {
  if (n == null || Number.isNaN(n)) return '—';
  if (!Number.isFinite(n)) return '∞';
  const abs = Math.abs(n);
  let d = decimals;
  if (abs > 0 && abs < 0.01) d = Math.max(d, 6);
  else if (abs >= 10000) d = 0;
  else if (abs >= 100) d = Math.max(d, 2);
  return n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
};

/**
 * Percentage already in 0–100 range (engine: win_rate / total_return_pct / max_drawdown_pct * 100).
 * Never multiplies. Infinity → '—'
 */
export const safePct = (
  n: number | null | undefined,
  opts: { signed?: boolean } = { signed: true },
): string => {
  if (n == null || Number.isNaN(n) || !Number.isFinite(n)) return '—';
  const signed = opts.signed !== false;
  const sign = signed && n > 0 ? '+' : '';
  return `${sign}${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
};

/** Convert 0–1 fraction to % string (e.g. trade pnl_pct) */
export const fracToPct = (n: number | null | undefined, opts: { signed?: boolean } = { signed: true }): string => {
  if (n == null || Number.isNaN(n) || !Number.isFinite(n)) return '—';
  return safePct(n * 100, opts);
};

export const safeSigned = (n: number | null | undefined, decimals = 2): string => {
  if (n == null || Number.isNaN(n)) return '—';
  if (!Number.isFinite(n)) return '∞';
  const body = safeFmt(n, decimals);
  if (n > 0) return `+${body}`;
  return body; // already has '-' if negative
};

export const safeInt = (n: number | null | undefined): string => {
  if (n == null || Number.isNaN(n)) return '—';
  if (!Number.isFinite(n)) return '∞';
  return Math.round(n).toLocaleString('en-US');
};

export const formatPrice = (n: number | null | undefined): string => {
  if (n == null || !Number.isFinite(Number(n))) return '—';
  const v = Number(n);
  const abs = Math.abs(v);
  let d = 2;
  if (abs > 0 && abs < 0.01) d = 6;
  else if (abs < 1) d = 4;
  else if (abs >= 1000) d = 2;
  return v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
};

export const formatQty = (n: number | null | undefined): string => {
  if (n == null || !Number.isFinite(Number(n))) return '—';
  const v = Number(n);
  const abs = Math.abs(v);
  const d = abs > 0 && abs < 0.001 ? 6 : abs < 1 ? 4 : 2;
  return v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
};
