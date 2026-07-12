from __future__ import annotations

from typing import Any

from app.models.schemas import StrategyTemplate
from strategies.base import StrategyBase


_registry: dict[str, type[StrategyBase]] = {}


def register_strategy(cls: type[StrategyBase]) -> type[StrategyBase]:
    _registry[cls.name] = cls
    return cls


def get_strategy(name: str) -> type[StrategyBase]:
    if name not in _registry:
        raise KeyError(f"Strategy '{name}' not found. Available: {list(_registry)}")
    return _registry[name]


def list_templates() -> list[StrategyTemplate]:
    return [
        StrategyTemplate(
            id=name,
            name=cls.description or name,
            description=cls.__doc__ or "",
            category=getattr(cls, "category", ""),
            params=[],
        )
        for name, cls in _registry.items()
    ]


# ponytail: lazy import — register on first access
def _ensure_registered() -> None:
    if not _registry:
        from strategies.technical.moving_average import MovingAverageCrossStrategy  # noqa: F811
        from strategies.technical.breakout import BreakoutStrategy
        from strategies.technical.pairs import PairsTradingStrategy
        from strategies.technical.arbitrage import StatisticalArbitrageStrategy

        register_strategy(MovingAverageCrossStrategy)
        register_strategy(BreakoutStrategy)
        register_strategy(PairsTradingStrategy)
        register_strategy(StatisticalArbitrageStrategy)


_ensure_registered()