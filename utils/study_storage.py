"""
Optuna Study 持久化模組

- SQLite: 儲存所有 study 與 trial 的 metadata（參數、值、狀態）
- Parquet: 儲存每個 trial 的完整回測結果（權益曲線、交易記錄、metrics）

提供:
- load_or_create_study(): 載入或建立 Study（含 SQLite 連接）
- save_trial_result(): 儲存 trial 完整結果到 Parquet
- load_trial_result(): 載入特定 trial 的結果
- list_studies(): 列出所有 study
- load_study_summary(): 載入 study 摘要
"""
from __future__ import annotations

import os
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

import pandas as pd
import numpy as np


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# === 路徑配置 ===

# 專案根目錄
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
# 主要 DB（Optuna 用的）+ 元資料 DB（我們自己寫的）
# 分兩個檔避免 SQLite lock 衝突
DB_PATH = DATA_DIR / "optuna_studies.db"
META_DB_PATH = DATA_DIR / "study_metadata.db"
TRIALS_DIR = DATA_DIR / "trials"


def _ensure_dirs():
    """確保目錄存在"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TRIALS_DIR.mkdir(parents=True, exist_ok=True)


# === SQLite 元數據 ===

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS studies (
    study_name TEXT PRIMARY KEY,
    direction TEXT NOT NULL,
    sampler TEXT,
    pruner TEXT,
    n_trials INTEGER DEFAULT 0,
    best_value REAL,
    best_params_json TEXT,
    extra_config_json TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS trial_metadata (
    trial_id INTEGER,
    study_name TEXT,
    number INTEGER,
    value REAL,
    state TEXT,
    params_json TEXT,
    user_attrs_json TEXT,
    system_attrs_json TEXT,
    datetime_start TEXT,
    datetime_complete TEXT,
    PRIMARY KEY (study_name, number),
    FOREIGN KEY (study_name) REFERENCES studies(study_name)
);

CREATE INDEX IF NOT EXISTS idx_trial_study ON trial_metadata(study_name);
CREATE INDEX IF NOT EXISTS idx_trial_value ON trial_metadata(value);
"""


def get_sqlite_url(study_name: str = "default_study") -> str:
    """
    取得 SQLite URL（Optuna 格式）

    Args:
        study_name: study 名稱

    Returns:
        Optuna 用的 storage URL
    """
    _ensure_dirs()
    return f"sqlite:///{DB_PATH}"


def _connect():
    """取得元資料 DB 連接（與 Optuna RDBStorage 分開）"""
    _ensure_dirs()
    conn = sqlite3.connect(str(META_DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    # 啟用 WAL 模式避免 lock 問題
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    return conn


def init_db():
    """初始化資料庫 schema"""
    _ensure_dirs()
    with _connect() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def save_study_meta(
    study_name: str,
    direction: str,
    sampler: str,
    pruner: Optional[str],
    n_trials: int,
    best_value: Optional[float],
    best_params: Optional[Dict[str, Any]],
    extra_config: Optional[Dict[str, Any]] = None,
):
    """儲存 study 的 metadata"""
    init_db()
    now = _utc_now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO studies (study_name, direction, sampler, pruner, n_trials, best_value, best_params_json, extra_config_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(study_name) DO UPDATE SET
                n_trials = excluded.n_trials,
                best_value = excluded.best_value,
                best_params_json = excluded.best_params_json,
                extra_config_json = excluded.extra_config_json,
                updated_at = excluded.updated_at
            """,
            (
                study_name, direction, sampler, pruner, n_trials, best_value,
                json.dumps(best_params or {}, default=str),
                json.dumps(extra_config or {}, default=str),
                now, now,
            ),
        )
        conn.commit()


def save_trial_meta(
    study_name: str,
    number: int,
    value: Optional[float],
    state: str,
    params: Dict[str, Any],
    user_attrs: Optional[Dict[str, Any]] = None,
    system_attrs: Optional[Dict[str, Any]] = None,
    datetime_start: Optional[str] = None,
    datetime_complete: Optional[str] = None,
):
    """儲存單個 trial 的 metadata"""
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO trial_metadata (study_name, number, value, state, params_json, user_attrs_json, system_attrs_json, datetime_start, datetime_complete)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(study_name, number) DO UPDATE SET
                value = excluded.value,
                state = excluded.state,
                params_json = excluded.params_json,
                user_attrs_json = excluded.user_attrs_json,
                system_attrs_json = excluded.system_attrs_json,
                datetime_complete = excluded.datetime_complete
            """,
            (
                study_name, number, value, state,
                json.dumps(params, default=str),
                json.dumps(user_attrs or {}, default=str),
                json.dumps(system_attrs or {}, default=str),
                datetime_start or _utc_now(),
                datetime_complete or _utc_now(),
            ),
        )
        conn.commit()


# === Parquet 完整結果 ===

def save_trial_result(
    study_name: str,
    trial_number: int,
    metrics: Dict[str, Any],
    params: Dict[str, Any],
    trades: Optional[List[Dict]] = None,
    equity_curve: Optional[pd.DataFrame] = None,
) -> Path:
    """
    儲存 trial 完整結果到 Parquet

    Args:
        study_name: study 名稱
        trial_number: trial 編號
        metrics: 績效指標 dict
        params: 該 trial 的參數
        trades: 交易記錄 list of dict
        equity_curve: 權益曲線 DataFrame

    Returns:
        Parquet 檔案路徑
    """
    _ensure_dirs()
    safe_name = study_name.replace("/", "_").replace(" ", "_")
    file_path = TRIALS_DIR / f"{safe_name}_{trial_number:06d}.parquet"

    # 構造要儲存的資料
    payload = {
        "study_name": study_name,
        "trial_number": trial_number,
        "saved_at": _utc_now(),
        "params": json.dumps(params, default=str),
        "metrics": json.dumps(_jsonable(metrics), default=str),
    }

    # 額外的 DataFrame（存成 dict 格式以相容 parquet）
    if equity_curve is not None and not equity_curve.empty:
        payload["equity_curve"] = json.dumps(equity_curve.reset_index().to_dict(orient="records"), default=str)
    else:
        payload["equity_curve"] = None

    if trades is not None and len(trades) > 0:
        # trades 是 list of dict，轉成 JSON 字串
        payload["trades"] = json.dumps(trades, default=str)
    else:
        payload["trades"] = None

    df = pd.DataFrame([payload])
    df.to_parquet(file_path, index=False)
    return file_path


def _jsonable(obj):
    """把 numpy 物件轉成 JSON 可序列化"""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    return obj


def load_trial_result(study_name: str, trial_number: int) -> Optional[Dict[str, Any]]:
    """
    載入特定 trial 的完整結果

    Returns:
        dict with keys: study_name, trial_number, params, metrics, equity_curve, trades
        或 None（檔案不存在）
    """
    safe_name = study_name.replace("/", "_").replace(" ", "_")
    file_path = TRIALS_DIR / f"{safe_name}_{trial_number:06d}.parquet"
    if not file_path.exists():
        return None

    df = pd.read_parquet(file_path)
    if df.empty:
        return None

    row = df.iloc[0]
    result = {
        "study_name": row["study_name"],
        "trial_number": int(row["trial_number"]),
        "saved_at": row["saved_at"],
        "params": json.loads(row["params"]),
        "metrics": json.loads(row["metrics"]),
        "equity_curve": json.loads(row["equity_curve"]) if row.get("equity_curve") else None,
        "trades": json.loads(row["trades"]) if row.get("trades") else None,
    }
    return result


def list_studies() -> pd.DataFrame:
    """列出所有 study"""
    init_db()
    with _connect() as conn:
        df = pd.read_sql_query("SELECT * FROM studies ORDER BY updated_at DESC", conn)
    return df


def list_trial_metadata(study_name: str) -> pd.DataFrame:
    """列出指定 study 的所有 trial metadata"""
    init_db()
    with _connect() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM trial_metadata WHERE study_name = ? ORDER BY number",
            conn,
            params=(study_name,),
        )
    if not df.empty and "params_json" in df.columns:
        df["params"] = df["params_json"].apply(lambda x: json.loads(x) if x else {})
    return df


def delete_study(study_name: str, delete_parquet: bool = True):
    """刪除 study（含所有 parquet）"""
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM trial_metadata WHERE study_name = ?", (study_name,))
        conn.execute("DELETE FROM studies WHERE study_name = ?", (study_name,))
        conn.commit()

    if delete_parquet:
        safe_name = study_name.replace("/", "_").replace(" ", "_")
        for f in TRIALS_DIR.glob(f"{safe_name}_*.parquet"):
            try:
                f.unlink()
            except Exception:
                pass


def get_study_summary(study_name: str) -> Optional[Dict[str, Any]]:
    """取得 study 摘要"""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM studies WHERE study_name = ?", (study_name,)
        ).fetchone()
    if not row:
        return None
    return {
        "study_name": row["study_name"],
        "direction": row["direction"],
        "sampler": row["sampler"],
        "pruner": row["pruner"],
        "n_trials": row["n_trials"],
        "best_value": row["best_value"],
        "best_params": json.loads(row["best_params_json"]) if row["best_params_json"] else {},
        "extra_config": json.loads(row["extra_config_json"]) if row["extra_config_json"] else {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


BACKTEST_RESULTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT,
    symbol TEXT,
    timeframe TEXT,
    strategy_name TEXT,
    params_json TEXT,
    metrics_json TEXT,
    trades_json TEXT,
    equity_curve_json TEXT
);
"""


def save_backtest_result(
    symbol: str,
    timeframe: str,
    strategy_name: str,
    params: Dict[str, Any],
    metrics: Dict[str, Any],
    trades: Optional[List[Dict]] = None,
    equity_curve: Optional[pd.DataFrame] = None,
) -> int:
    """儲存單次回測結果到 SQLite，回傳新增的 id"""
    init_db()
    with _connect() as conn:
        conn.executescript(BACKTEST_RESULTS_SCHEMA)
        ec_json = None
        if equity_curve is not None and not equity_curve.empty:
            ec_json = json.dumps(equity_curve.reset_index().to_dict(orient="records"), default=str)
        cursor = conn.execute(
            """INSERT INTO backtest_results
               (created_at, symbol, timeframe, strategy_name, params_json, metrics_json, trades_json, equity_curve_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _utc_now(), symbol, timeframe, strategy_name,
                json.dumps(_jsonable(params), default=str),
                json.dumps(_jsonable(metrics), default=str),
                json.dumps(_jsonable(trades), default=str) if trades else None,
                ec_json,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def load_backtest_result(result_id: int) -> Optional[Dict[str, Any]]:
    """載入指定的回測結果"""
    init_db()
    with _connect() as conn:
        conn.executescript(BACKTEST_RESULTS_SCHEMA)
        row = conn.execute(
            "SELECT * FROM backtest_results WHERE id = ?", (result_id,)
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "symbol": row["symbol"],
        "timeframe": row["timeframe"],
        "strategy_name": row["strategy_name"],
        "params": json.loads(row["params_json"]) if row["params_json"] else {},
        "metrics": json.loads(row["metrics_json"]) if row["metrics_json"] else {},
        "trades": json.loads(row["trades_json"]) if row["trades_json"] else None,
        "equity_curve": json.loads(row["equity_curve_json"]) if row["equity_curve_json"] else None,
    }


def list_backtest_results(symbol: Optional[str] = None) -> pd.DataFrame:
    """列出回測結果（不含 trades/equity_curve 以節省記憶體）"""
    init_db()
    with _connect() as conn:
        conn.executescript(BACKTEST_RESULTS_SCHEMA)
        if symbol:
            df = pd.read_sql_query(
                "SELECT id, created_at, symbol, timeframe, strategy_name, metrics_json FROM backtest_results WHERE symbol = ? ORDER BY id DESC",
                conn, params=(symbol,)
            )
        else:
            df = pd.read_sql_query(
                "SELECT id, created_at, symbol, timeframe, strategy_name, metrics_json FROM backtest_results ORDER BY id DESC",
                conn
            )
    return df


__all__ = [
    "get_sqlite_url",
    "init_db",
    "save_study_meta",
    "save_trial_meta",
    "save_trial_result",
    "load_trial_result",
    "list_studies",
    "list_trial_metadata",
    "delete_study",
    "get_study_summary",
    "save_backtest_result",
    "load_backtest_result",
    "list_backtest_results",
    "DATA_DIR",
    "DB_PATH",
    "TRIALS_DIR",
]
