from __future__ import annotations

from abc import abstractmethod
from typing import Any, Optional, Protocol

import numpy as np
import pandas as pd

from strategies.base import Bar, Signal, StrategyBase


# ponytail: Protocol avoids introducing sklearn/torch deps
class BasePredictor(Protocol):
    def predict(self, features: np.ndarray) -> np.ndarray: ...
    def predict_proba(self, features: np.ndarray) -> np.ndarray: ...


class FeatureEngine(Protocol):
    def transform(self, df: pd.DataFrame) -> np.ndarray: ...


class MLStrategy(StrategyBase):
    """ML 策略基類（預留接口，暫不實装）。"""

    name = "ml_strategy"
    description = "ML 策略基類（預留接口）"
    category = "ml"

    def __init__(self) -> None:
        super().__init__()
        self.model: Optional[BasePredictor] = None
        self.feature_engineering: Optional[FeatureEngine] = None

    def init(self, params: dict[str, Any]) -> None:
        self.entry_threshold: float = params.get("entry_threshold", 0.6)
        self.lookback: int = params.get("lookback", 100)

    @abstractmethod
    def load_model(self, model_path: str) -> None:
        raise NotImplementedError("ML model loading not implemented yet")

    def extract_features(self, df: pd.DataFrame) -> np.ndarray:
        if self.feature_engineering is not None:
            return self.feature_engineering.transform(df)
        returns = df["close"].pct_change().fillna(0).values
        return returns.reshape(-1, 1)

    def predict(self, features: np.ndarray) -> float:
        if self.model is None:
            raise RuntimeError("ML model not loaded")
        pred = self.model.predict(features)
        return float(pred[-1]) if hasattr(pred, "__len__") else float(pred)

    def next(self, bar: Bar) -> Optional[Signal]:
        return None

    def get_params(self) -> dict[str, Any]:
        return {"entry_threshold": getattr(self, "entry_threshold", 0.6), "lookback": getattr(self, "lookback", 100)}