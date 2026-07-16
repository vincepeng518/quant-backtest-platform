from __future__ import annotations

"""Experiment store — versioned backtest / optimization runs (borrowed from Qlib's Recorder).

Every backtest or optimization run can be recorded as an "experiment" with a
snapshot of its config + key metrics. This enables horizontal comparison and
reproducibility (re-run later, diff against a previous version).

Storage: JSON lines under data/experiments/<id>.json (git-persisted).
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any, Optional

EXP_DIR = Path(__file__).resolve().parents[1] / "data" / "experiments"
EXP_DIR.mkdir(parents=True, exist_ok=True)


def _path(eid: str) -> Path:
    return EXP_DIR / f"{eid}.json"


def save_experiment(
    kind: str,
    config: dict,
    metrics: dict,
    label: Optional[str] = None,
) -> dict:
    """Persist an experiment. Returns the stored record."""
    eid = uuid.uuid4().hex[:12]
    record = {
        "id": eid,
        "kind": kind,  # 'backtest' | 'optimize'
        "label": label or f"{kind}-{eid}",
        "created_at": time.time(),
        "config": config,
        "metrics": metrics,
    }
    _path(eid).write_text(json.dumps(record, default=str, indent=2))
    return record


def list_experiments(kind: Optional[str] = None) -> list[dict]:
    out = []
    for p in EXP_DIR.glob("*.json"):
        try:
            rec = json.loads(p.read_text())
        except Exception:
            continue
        if kind and rec.get("kind") != kind:
            continue
        out.append(rec)
    out.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    return out


def get_experiment(eid: str) -> Optional[dict]:
    p = _path(eid)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def compare_experiments(ids: list[str]) -> dict:
    """Side-by-side comparison of selected experiments' metrics."""
    rows = []
    for eid in ids:
        rec = get_experiment(eid)
        if rec:
            rows.append(rec)
    if not rows:
        return {"experiments": [], "metric_keys": []}
    metric_keys = sorted({k for r in rows for k in r.get("metrics", {}).keys()})
    return {"experiments": rows, "metric_keys": metric_keys}
