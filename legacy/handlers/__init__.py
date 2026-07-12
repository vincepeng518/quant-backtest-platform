"""事件處理器基底類別"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List
from events import Event


class EventHandler(ABC):
    """事件處理器基底類別"""

    @abstractmethod
    def handle(self, event: Event) -> List[Event]:
        """
        處理事件，產出 0 到多個新事件

        Args:
            event: 輸入事件

        Returns:
            產出的事件列表（空 list 表示無產出）
        """
        raise NotImplementedError
