import { checkPythonSyntax } from '../src/lib/pythonSyntax.ts';
const SAMPLE = `from __future__ import annotations
from typing import Any, Optional

from strategies.base import Bar, Signal, StrategyBase


class MyStrategy(StrategyBase):
    description = "My custom strategy"
    category = "custom"

    def get_params_space(self):
        return {"fast_period": (5, 50, 1), "slow_period": (20, 200, 1)}

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.fast_period = int(params.get("fast_period", 20))
        self.slow_period = int(params.get("slow_period", 50))
        self.prices: list[float] = []
        self._pos = 0

    def next(self, bar: Bar) -> Optional[Signal]:
        self.prices.append(bar.close)
        if len(self.prices) < self.slow_period:
            return None
        fast_ma = sum(self.prices[-self.fast_period :]) / self.fast_period
        slow_ma = sum(self.prices[-self.slow_period :]) / self.slow_period
        prev_fast = sum(self.prices[-self.fast_period - 1 : -1]) / self.fast_period
        prev_slow = sum(self.prices[-self.slow_period - 1 : -1]) / self.slow_period
        golden = prev_fast <= prev_slow and fast_ma > slow_ma
        death = prev_fast >= prev_slow and fast_ma < slow_ma
        if golden and self._pos <= 0:
            self._pos = 1
            return Signal(action="buy", price=bar.close)
        if death and self._pos >= 0:
            self._pos = -1
            return Signal(action="sell", price=bar.close)
        return None
`;
const r = checkPythonSyntax(SAMPLE);
console.log('SAMPLE 策略 ok =', r.ok, '(期望 true)');
if (!r.ok) console.log('診斷:', r.diagnostics.map(d=>`r${d.rule}@L${d.line}:${d.message}`));
const t0=performance.now(); checkPythonSyntax(SAMPLE); const dt=performance.now()-t0;
console.log(`SAMPLE 檢查耗時: ${dt.toFixed(3)}ms`);
console.log(r.ok ? '✓ 舊有策略載入編輯器不誤報,可正常編輯/提交' : '✗ SAMPLE 被誤判!');
process.exit(r.ok ? 0 : 1);
