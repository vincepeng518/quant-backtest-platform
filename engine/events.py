from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

import pandas as pd


class EventType(str, Enum):
    BAR = "bar"
    SIGNAL = "signal"
    ORDER = "order"
    FILL = "fill"
    SLTP = "sltp"


@dataclass
class Event:
    type: EventType
    timestamp: pd.Timestamp
    data: dict = field(default_factory=dict)


class EventEmitter:
    """輕量事件發射器。"""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, event: str, handler: Callable) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def emit(self, event: str, data: Any = None) -> None:
        for handler in self._handlers.get(event, []):
            handler(data)

    def off(self, event: str, handler: Callable) -> None:
        self._handlers.get(event, []).remove(handler)