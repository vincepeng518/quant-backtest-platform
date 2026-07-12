from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path("./data/csv")


class CSVLoader:
    """Load OHLCV data from local CSV files."""

    def __init__(self, data_dir: str = "") -> None:
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR

    def load(self, symbol: str, filepath: str = "") -> Optional[pd.DataFrame]:
        """Load OHLCV CSV. Falls back to a symbol-named file under data_dir."""
        if filepath:
            path = Path(filepath)
        else:
            path = self.data_dir / f"{symbol.replace('/', '_')}.csv"

        if not path.exists():
            logger.warning("CSV not found: %s", path)
            return None

        try:
            df = pd.read_csv(path)
        except Exception as e:
            logger.warning("CSV load failed for %s: %s", path, e)
            return None

        # Normalize column names
        rename = {}
        for col in df.columns:
            cl = col.lower().strip()
            if cl in ("timestamp", "time", "date", "datetime"):
                rename[col] = "timestamp"
            elif cl in ("open", "o"):
                rename[col] = "open"
            elif cl in ("high", "h"):
                rename[col] = "high"
            elif cl in ("low", "l"):
                rename[col] = "low"
            elif cl in ("close", "c"):
                rename[col] = "close"
            elif cl in ("volume", "vol", "v"):
                rename[col] = "volume"
        df = df.rename(columns=rename)

        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            logger.warning("CSV missing required columns: %s", required - set(df.columns))
            return None

        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        return df[["timestamp", "open", "high", "low", "close", "volume"]].dropna()
