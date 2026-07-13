from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

@dataclass
class FundingSchedule:
    interval_hours: int = 8
    rates: pd.Series = field(default_factory=pd.Series)  # index=Timestamp, value=rate fraction

class FundingModel:
    def __init__(self, schedule: Optional[FundingSchedule] = None, default_rate: float = 0.0):
        self.schedule = schedule
        self.default_rate = default_rate

    def rate_at(self, ts: pd.Timestamp) -> float:
        if self.schedule is None or self.schedule.rates.dropna().empty:
            return self.default_rate
        s = self.schedule.rates[self.schedule.rates.index <= ts]
        return float(s.iloc[-1]) if not s.empty else self.default_rate

    def accrued(self, entry: pd.Timestamp, exit: pd.Timestamp, side: int) -> float:
        """Signed funding as fraction of notional. Long(side=1) pays positive rate.

        Falls back to interval-based accrual (interval_hours + default_rate) when
        no explicit rate schedule is supplied — matches the perpetual backtester's
        behaviour so a config without a rates table still captures funding.
        """
        if self.schedule is not None and not self.schedule.rates.dropna().empty:
            s = self.schedule.rates[(self.schedule.rates.index > entry) & (self.schedule.rates.index <= exit)]
            total = float(s.sum())
            return total * side  # long pays positive funding out (negative pnl)
        # Interval-based fallback
        if self.schedule is not None and self.schedule.interval_hours > 0 and self.default_rate != 0.0:
            hours = (exit - entry).total_seconds() / 3600.0
            periods = max(0, int(hours // self.schedule.interval_hours))
            return self.default_rate * periods * side
        return 0.0
