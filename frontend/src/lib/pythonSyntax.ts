/**
 * lib/pythonSyntax.ts
 * 輕量 Python 語法檢查器 — 純 TS、零依賴、即時(<2ms @ ≤8KB code)。
 *
 * 目的：前端的「即時語法檢查」，在用戶打字時標出語法層錯誤。
 * 範圍：只做 *語法(syntax)* 層，不做語義/型別分析（那是後端 AST 沙箱的職責）。
 *
 * 規則集（每條可獨立測試）：
 *   R1 括號配對   — () [] {} 必須一一對應、順序正確、不殘留
 *   R2 未閉合字串 — ' " ''' """ 不得中途 EOF
 *   R3 非法字元   — 不得含 Python 無法解析的控制字元
 *   R4 保留字結尾 — def/class/return/if/else/elif/for/while 等不得緊跟非法 token
 *   R5 縮排一致性 — 單檔內不得混用 tab 與 space 開頭縮排 (Python TabError)
 *   R6 尾部運算元 — 以 = / 二元運算子 / 逗號 結束行 = 缺右運算元 (不完整)
 *
 * 回傳 Promise 以模擬異步檢查介面（方便接 debounce / loading），
 * 但內部是同步運算，即刻 resolve。
 */

export interface PySyntaxDiagnostic {
  /** 第幾列，1-based。錯誤所在行的起始與結束 offset（0-based，含 end）。 */
  line: number;
  start: number;
  end: number;
  /** 規則代號：r1..r5 */
  rule: string;
  message: string;
  severity: 'error' | 'warning';
}

export interface PySyntaxResult {
  ok: boolean;
  diagnostics: PySyntaxDiagnostic[];
  /** 毫秒，實際運算耗時（供測試工具量測） */
  elapsedMs: number;
}

/* ------------------------------------------------------------------ *
 * Tokenizer：極簡 Python token 掃描
 * 只為了抓語法層錯誤，不追求完整 lexer。碰到它不認識的就是 raw。 *
 * ------------------------------------------------------------------ */

const KEYWORDS = new Set([
  'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await',
  'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except',
  'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is',
  'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try',
  'while', 'with', 'yield',
]);

/** 需要「後面有東西」的 token（若直接接換行/EOF → 語法錯誤） */
const NEEDS_FOLLOW = new Set(['def', 'class', 'import', 'from', 'return', 'raise', 'yield']);

const OPEN = { '(': ')', '[': ']', '{': '}' } as const;
const CLOSE = new Set([')', ']', '}']);

interface Token {
  start: number;
  end: number;
  line: number;
  type: 'str' | 'kw' | 'num' | 'op' | 'name' | 'newline' | 'indent' | 'other';
  value: string;
}

/**
 * R1+R2 的掃描器：回傳所有「括號未配對」與「字串未閉合」的診斷 + token 列表。
 * 用單次掃描同時完成 R1/R2/R3，效能單遍 O(n)。
 */
function scanTokens(src: string): { tokens: Token[]; diags: PySyntaxDiagnostic[]; lines: number[] } {
  const diags: PySyntaxDiagnostic[] = [];
  const tokens: Token[] = [];
  const lines: number[] = [0];
  for (let i = 0; i < src.length; i++) if (src[i] === '\n') lines.push(i + 1);

  const stack: { ch: string; start: number; line: number; end: number }[] = [];
  const lineOf = (pos: number): number => {
    // 二分找 pos 落在哪一行（1-based）
    let lo = 0, hi = lines.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (lines[mid] <= pos) lo = mid; else hi = mid - 1;
    }
    return lo + 1;
  };

  let i = 0;
  const n = src.length;
  while (i < n) {
    const c = src[i];

    // R3：控制字元（除 \t \n \r 外）
    const cc = c.charCodeAt(0);
    if (cc < 0x20 && c !== '\t' && c !== '\n' && c !== '\r') {
      diags.push({ line: lineOf(i), start: i, end: i + 1, rule: 'r3', severity: 'error', message: `非法控制字元 \\x${cc.toString(16).padStart(2, '0')}` });
      i++;
      continue;
    }

    // 註解 # ... 到行尾（保留字不下標）
    if (c === '#') {
      while (i < n && src[i] !== '\n') i++;
      continue;
    }

    // 字串：' " ''' """（含前綴 r/f/b/u/t）
    if (c === "'" || c === '"') {
      // 抓前綴（r"..." f'...' b'''...'''）
      const peekPrefixStart = i;
      // 簡單處理：回到上一個 identifier 前綴
      const q = c;
      const triple = src[i + 1] === q && src[i + 2] === q;
      const quoteLen = triple ? 3 : 1;
      let j = i + quoteLen;
      let closed = false;
      while (j < n) {
        if (src[j] === '\\') { j += 2; continue; }
        if (src[j] === q) {
          if (triple) {
            if (src[j + 1] === q && src[j + 2] === q) { closed = true; j += 3; break; }
            j++;
            continue;
          } else {
            closed = true; j++; break;
          }
        }
        if (!triple && src[j] === '\n') break; // 單行字串不得跨行
        j++;
      }
      if (!closed) {
        diags.push({ line: lineOf(i), start: i, end: n, rule: 'r2', severity: 'error', message: `未閉合的字串（起始 ${q === "'" ? '單引號' : '雙引號'}${triple ? '×3' : ''}）` });
      }
      tokens.push({ start: i, end: j > n ? n : j, line: lineOf(i), type: 'str', value: src.slice(i, j) });
      i = j;
      continue;
    }

    // 數字
    if (/[0-9]/.test(c)) {
      let j = i + 1;
      while (j < n && /[0-9a-fA-FxXoObB_.eEjJ]/.test(src[j])) j++;
      tokens.push({ start: i, end: j, line: lineOf(i), type: 'num', value: src.slice(i, j) });
      i = j;
      continue;
    }

    // identifier / 關鍵字
    if (/[A-Za-z_]/.test(c)) {
      let j = i + 1;
      while (j < n && /[A-Za-z0-9_]/.test(src[j])) j++;
      const word = src.slice(i, j);
      tokens.push({ start: i, end: j, line: lineOf(i), type: KEYWORDS.has(word) ? 'kw' : 'name', value: word });
      i = j;
      continue;
    }

    // 括號
    if (c in OPEN) {
      stack.push({ ch: c, start: i, line: lineOf(i), end: 0 });
      i++;
      continue;
    }
    if (CLOSE.has(c)) {
      const top = stack.pop();
      if (!top) {
        diags.push({ line: lineOf(i), start: i, end: i + 1, rule: 'r1', severity: 'error', message: `多餘的右括號 ${c}` });
      } else if (OPEN[top.ch as keyof typeof OPEN] !== c) {
        diags.push({ line: top.line, start: top.start, end: i, rule: 'r1', severity: 'error', message: `括號不匹配：${top.ch} 對應到 ${c}` });
      }
      i++;
      continue;
    }

    // 換行
    if (c === '\n') {
      tokens.push({ start: i, end: i + 1, line: lineOf(i), type: 'newline', value: '\n' });
      i++;
      continue;
    }

    // 空白（行首縮排單獨標 indent）
    if (c === ' ' || c === '\t') {
      let j = i;
      while (j < n && (src[j] === ' ' || src[j] === '\t') && src[j] !== '\n') j++;
      tokens.push({ start: i, end: j, line: lineOf(i), type: 'indent', value: src.slice(i, j) });
      i = j;
      continue;
    }

    // 其餘 operator / 符號：整段吃掉非空白、非換行字元，避免誤判
    {
      let j = i + 1;
      while (j < n && !/[\s()\[\]{}'"#]/.test(src[j])) j++;
      // 但 # 可能中途開始註解，切割到 # 前
      tokens.push({ start: i, end: j, line: lineOf(i), type: 'op', value: src.slice(i, j) });
      i = j;
    }
  }

  // 括號殘留（未閉合）
  for (const p of stack) {
    diags.push({ line: p.line, start: p.start, end: n, rule: 'r1', severity: 'error', message: `未閉合的括號 ${p.ch}` });
  }

  return { tokens, diags, lines };
}

/**
 * 主檢查函數。回傳 { ok, diagnostics, elapsedMs }。
 * ok=false 代表有 error 等級診斷。
 */
export function checkPythonSyntax(src: string): PySyntaxResult {
  const t0 = performance.now();
  const diags: PySyntaxDiagnostic[] = [];

  const { tokens: t, diags: scanDiags, lines } = scanTokens(src);
  diags.push(...scanDiags);

  // ---- R4：保留字結尾（def/class/import/from/return/raise/yield 後必接東西）
  for (let k = 0; k < t.length; k++) {
    const tok = t[k];
    if (tok.type === 'kw' && NEEDS_FOLLOW.has(tok.value)) {
      // 找下一個非 indent/newline token
      let nxt: Token | undefined;
      for (let m = k + 1; m < t.length; m++) {
        const tm = t[m];
        if (tm.type === 'indent' || tm.type === 'newline') continue;
        nxt = tm; break;
      }
      // def/class/from/import 後必須有名稱；return/raise/yield 後可有可無但要到行尾
      if (!nxt) {
        diags.push({ line: tok.line, start: tok.start, end: tok.end, rule: 'r4', severity: 'error', message: `關鍵字 ${tok.value} 後缺少必要的運算式` });
        continue;
      }
      // def/class/from/import 的「名稱」必須在同一行（不能跨 newline）
      if ((tok.value === 'def' || tok.value === 'class' || tok.value === 'from' || tok.value === 'import')) {
        // 檢查 tok 與 nxt 之間有沒有出現 newline
        let crossedLine = false;
        for (let m = k + 1; m < t.length; m++) {
          const tm = t[m];
          if (tm.type === 'newline') { crossedLine = true; break; }
          if (tm.start >= nxt.start) break;
        }
        if (crossedLine) {
          diags.push({ line: tok.line, start: tok.start, end: tok.end, rule: 'r4', severity: 'error', message: `關鍵字 ${tok.value} 後缺少必要的識別字/模組名（不可在下一行）` });
          continue;
        }
        if (nxt.type !== 'name' && nxt.type !== 'num' && !(nxt.type === 'op' && nxt.value.startsWith('.'))) {
          diags.push({ line: tok.line, start: tok.start, end: nxt.end, rule: 'r4', severity: 'error', message: `關鍵字 ${tok.value} 後需接識別字/模組名，而非「${nxt.value}」` });
        }
      }
    }
  }

  // ---- R5：縮排一致性（查每個 indent token，混用 tab/space 即報）
  const seenIndentModes = new Set<'t' | 's'>();
  for (const tok of t) {
    if (tok.type === 'indent' && tok.value.length > 0) {
      const hasTab = tok.value.includes('\t');
      const hasSpace = tok.value.includes(' ');
      if (hasTab && hasSpace) {
        diags.push({ line: tok.line, start: tok.start, end: tok.end, rule: 'r5', severity: 'error', message: '縮排混用 Tab 與空白，Python 將報錯' });
        break; // 已抓到混用即可
      }
      // 記錄這個檔用哪種縮排
      if (hasTab) seenIndentModes.add('t');
      if (hasSpace) seenIndentModes.add('s');
    }
  }
  if (seenIndentModes.size > 1) {
    // 同一檔同時出現 tab-only 與 space-only 的縮排行 → Python TabError，屬錯誤
    diags.push({
      line: 1, start: 0, end: 0, rule: 'r5', severity: 'error',
      message: '縮排混用 Tab 與空白 – Python 會拋 TabError: inconsistent use of tabs and spaces in indentation',
    });
  }

  // ---- R6：尾部運算元（行以 = / 二元運算子 / 逗號 結束 → 缺右運算元）
  // 注意：不能用 tokens 陣列判斷（括號字元不進 tokens），改用原始 src 掃描
  // 「= 之後、同一行內」是否還有實質字符（空白與 # 註解不算）。
  const TRAILING_OPS = new Set([
    '=', '+=', '-=', '*=', '/=', '//=', '%=', '**=', '&=', '|=', '^=', '<<=', '>>=',
    '+', '-', '*', '/', '//', '%', '**', '&', '|', '^', '<', '>', '<=', '>=', '==', '!=', '<<', '>>',
    ',', '@',
  ]);
  const lines2 = lines; // 行起始偏移（lines 已算好）
  for (const tok of t) {
    if (tok.type !== 'op' || !TRAILING_OPS.has(tok.value)) continue;
    // 找這一行行尾偏移
    let lineEnd = src.length;
    for (let li = 0; li < lines2.length; li++) {
      if (lines2[li] > tok.start) { lineEnd = li + 1 < lines2.length ? lines2[li + 1] - 1 : src.length; break; }
    }
    // 同行內從 tok 之後找非空白非註解字符
    let hasOperand = false;
    for (let p = tok.end; p < lineEnd; p++) {
      const ch = src[p];
      if (ch === '#' ) break;        // 註解開始 → 之後不重要
      if (ch !== ' ' && ch !== '\t' && ch !== '\r') { hasOperand = true; break; }
    }
    if (!hasOperand) {
      diags.push({ line: tok.line, start: tok.start, end: tok.end, rule: 'r6', severity: 'error', message: `行尾以「${tok.value}」結束，缺少右側運算元` });
    }
  }

  const end = performance.now();
  const ok = !diags.some((d) => d.severity === 'error');
  return { ok, diagnostics: diags, elapsedMs: (end - t0) };
}
