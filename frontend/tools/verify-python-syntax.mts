/**
 * tools/verify-python-syntax.mjs — 輸入測試工具
 * 驗證 checkPythonSyntax 是否於 0.1s(100ms)內標示錯誤,並逐規則記錄:
 *   規則內容 / 反應時間 / 下一個語法。
 *
 * 用法: node --experimental-strip-types tools/verify-python-syntax.mjs
 * (用 Node 22 原生 strip-types 直接 import .ts)
 */
import { checkPythonSyntax } from '../src/lib/pythonSyntax.ts';

const MS_LIMIT = 100; // 0.1s

const RULES = [
  {
    name: 'R1 括號未閉合',
    bad: 'def f(x:\n    return x\nfoo = bar(1, 2',
    good: 'def f(x):\n    return x\nfoo = bar(1, 2)\n',
    expectRule: 'r1',
  },
  {
    name: 'R2 字串未閉合',
    bad: 'name = "hello\nprint(name)',
    good: 'name = "hello"\nprint(name)\n',
    expectRule: 'r2',
  },
  {
    name: 'R3 控制字元',
    bad: 'class A:\n    pass\0not ok',
    good: 'class A:\n    pass\n',
    expectRule: 'r3',
  },
  {
    name: 'R4 保留字後缺運算式',
    bad: 'def\nx = 1\n',
    good: 'def f():\n    return 1\n',
    expectRule: 'r4',
  },
  {
    name: 'R5 縮排混用 tab+space',
    bad: 'if a:\n\treturn 1\n    return 2\n',
    good: 'if a:\n    return 1\n    return 2\n',
    expectRule: 'r5',
  },
  {
    name: 'R6 行尾缺運算元(截斷在賦值)',
    bad: 'class Foo:\n    def bar(self):\n        self.x = ',
    good: 'class Foo:\n    def bar(self):\n        self.x = 1\n',
    expectRule: 'r6',
  },
];

// 也量一份「大檔案」效能(full SAMPLE 規模)確認仍 <0.1s
const BIG = Array.from({ length: 60 }, (_, i) =>
  `class C${i}:\n    def m(self, a${i}):\n        # comment ${i}\n        return a${i} * ${i} + 1  # trailing\n`
).join('\n');

let allPass = true;
console.log('=== 逐規則輸入測試(要求 < 100ms 標示錯誤) ===\n');

for (const r of RULES) {
  const t0 = performance.now();
  const res = checkPythonSyntax(r.bad);
  const t1 = performance.now();
  const dt = t1 - t0;

  const badFlags = res.diagnostics.map((d) => d.rule);
  const triggered = res.diagnostics.some((d) => d.rule === r.expectRule);
  const goodRes = checkPythonSyntax(r.good);
  const goodClean = goodRes.ok;

  const passed = triggered && !res.ok && goodClean && dt < MS_LIMIT;
  if (!passed) allPass = false;

  console.log(`[${passed ? 'PASS' : 'FAIL'}] ${r.name}`);
  console.log(`   規則觸發: ${r.expectRule}(${triggered ? '✓' : '✗'})  錯誤判定: ${res.ok ? '✗未標錯' : '✓'}  控制組乾淨: ${goodClean ? '✓' : '✗'}  反應時間: ${dt.toFixed(3)}ms${dt < MS_LIMIT ? ' ✓' : ' ✗ >100ms'}`);
  console.log(`   診斷: ${res.diagnostics.map((d) => `r${d.rule}@L${d.line}:${d.message}`).join(' | ') || '(無)'}`);
  console.log(`   下一步(本規則後要驗的語法): 用「${r.good.trim().split('\n')[0]}…」確認修正後不再誤報\n`);
}

// 效能壓力測試:大檔案 ×5 次,量 P95
const times: number[] = [];
for (let i = 0; i < 6; i++) {
  const t0 = performance.now();
  checkPythonSyntax(BIG);
  times.push(performance.now() - t0);
}
times.sort((a, b) => a - b);
const p95 = times[Math.floor(times.length * 0.95)];
const bigPass = p95 < MS_LIMIT;
if (!bigPass) allPass = false;
console.log(`=== 大檔案效能(60 類定義,${BIG.length} chars) ===`);
console.log(`   6 次耗時(ms): ${times.map((t) => t.toFixed(2)).join(', ')}`);
console.log(`   P95: ${p95.toFixed(2)}ms  ${p95 < MS_LIMIT ? '✓ <100ms' : '✗ >100ms'}`);

console.log(`\n=== 總結: ${allPass ? '全部通過,滿足 <0.1s 標示錯誤' : '有 FAIL,需修正'}`);
process.exit(allPass ? 0 : 1);
