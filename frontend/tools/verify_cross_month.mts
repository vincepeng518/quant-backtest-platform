// 跨月拼序列去重/排序驗證 - 直接 fetch GitHub raw(不依賴 api.ts,避開 TS parameter property)
const BASE = 'https://raw.githubusercontent.com/vincepeng518/quant-backtest-platform/master';
const gh = async (p: string) => { const r = await fetch(`${BASE}/${p}`, { cache: 'no-store' }); if (r.status === 404) return []; const d = await r.json(); return Array.isArray(d) ? d : (d?.records ?? []); };

const fp = (r: any) => `${r.ts ?? ''}|${r.symbol ?? ''}|${r.side ?? ''}|${r.realizedProfit ?? ''}`;
const sortKey = (r: any) => Number(r.ts ?? 0);

const latest = await gh('trades/latest_trades.json');
const june = await gh('trades/by-month/2026-06.json');
const may = await gh('trades/by-month/2026-05.json');
const apr = await gh('trades/by-month/2025-04.json');

let records = [...latest].sort((a, b) => sortKey(b) - sortKey(a));
console.log('首載 latest:', records.length, '筆 (涵蓋月', JSON.stringify((await (await fetch(`${BASE}/trades/latest_trades.json`)).json()).months), ')');

for (const [name, more] of [['2026-06', june], ['2026-05', may], ['2025-04', apr]]) {
  const seen = new Set(records.map(fp));
  const added = more.filter((r: any) => !seen.has(fp(r)));
  records = [...records, ...added].sort((a, b) => sortKey(b) - sortKey(a));
  console.log(`補載 ${name}: ${more.length}筆 → 新增 ${added.length} → 累計 ${records.length}`);
}

let monotonic = true;
for (let i = 1; i < records.length; i++) if (sortKey(records[i - 1]) < sortKey(records[i])) monotonic = false;
const fps = records.map(fp);
const dupes = fps.filter((f, i) => fps.indexOf(f) !== i);

console.log('=== 跨月序列驗證 ===');
console.log('ts 降冪(排序不亂):', monotonic);
console.log('無重複(fp指紋):', dupes.length === 0, dupes.length ? `重複${dupes.length}筆` : '');
console.log('前3筆:', records.slice(0, 3).map(r => new Date(sortKey(r)).toISOString().slice(0, 16)));
console.log('後3筆:', records.slice(-3).map(r => new Date(sortKey(r)).toISOString().slice(0, 16)));
console.log('總筆數:', records.length);
