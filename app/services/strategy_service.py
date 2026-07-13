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
        from strategies.statistical.chainlink_updown import ChainlinkUpDownStrategy
        from strategies.statistical.polymarket_btc import PolymarketBtcStrategy

        register_strategy(MovingAverageCrossStrategy)
        register_strategy(BreakoutStrategy)
        register_strategy(PairsTradingStrategy)
        register_strategy(StatisticalArbitrageStrategy)
        register_strategy(ChainlinkUpDownStrategy)
        register_strategy(PolymarketBtcStrategy)
        load_user_strategies()


import importlib.util, json, uuid, logging
from pathlib import Path
from typing import Any
from strategies.base import StrategyBase
from app.services.strategy_git import git_persist

USER_DIR = Path(__file__).resolve().parents[2] / "strategies" / "user"
MANIFEST = USER_DIR / "manifest.json"
_MAX = 100
logger = logging.getLogger(__name__)

def _read_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    try:
        return json.loads(MANIFEST.read_text())
    except Exception:
        return []

def _write_manifest(data: list[dict]) -> None:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def _load_one(path: Path, sid: str) -> None:
    spec = importlib.util.spec_from_file_location(f"user_strat_{sid}", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for attr in vars(mod).values():
        if isinstance(attr, type) and issubclass(attr, StrategyBase) and attr is not StrategyBase:
            attr.name = f"user_{sid}"
            register_strategy(attr)
            return
    raise ValueError("No StrategyBase subclass found")

def load_user_strategies() -> None:
    if not USER_DIR.exists():
        return
    for p in USER_DIR.glob("*.py"):
        if p.name == ".gitkeep":
            continue
        try:
            _load_one(p, p.stem)
        except Exception as e:
            logger.warning("Failed loading %s: %s", p, e)

def _syntax_ok(code: str) -> tuple[bool, str]:
    try:
        compile(code, "<strategy>", "exec")
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError: {e.msg} (line {e.lineno})"

def upload_strategy(payload: dict) -> dict:
    code = payload.get("code", "")
    ok, err = _syntax_ok(code)
    if not ok:
        return {"error": err, "code": "SYNTAX_ERROR"}
    sid = uuid.uuid4().hex[:12]
    USER_DIR.mkdir(parents=True, exist_ok=True)
    path = USER_DIR / f"{sid}.py"
    path.write_text(code)
    meta = {
        "id": sid, "name": payload.get("name", f"strategy_{sid}"),
        "description": payload.get("description", ""),
        "category": payload.get("category", "custom"),
        "filename": f"{sid}.py", "created_at": _now(),
    }
    man = _read_manifest()
    if len(man) >= _MAX:
        logger.warning("Strategy count >= %d (soft limit)", _MAX)
    man.append(meta)
    _write_manifest(man)
    succ, detail = git_persist([str(path), str(MANIFEST)], f"feat(strategy): add {meta['name']}")
    if not succ:
        logger.warning("git push failed: %s", detail)
    try:
        _load_one(path, sid)
        meta["status"] = "registered"
    except Exception as e:
        meta["status"] = "error"
        meta["error"] = str(e)[:200]
    return meta

def list_user_strategies() -> list[dict]:
    return _read_manifest()

def get_user_strategy(sid: str) -> dict:
    man = _read_manifest()
    for m in man:
        if m["id"] == sid:
            m = dict(m)
            m["code"] = (USER_DIR / m["filename"]).read_text()
            return m
    return {"error": "not found"}

def update_strategy(sid: str, payload: dict) -> dict:
    man = _read_manifest()
    for m in man:
        if m["id"] == sid:
            code = payload.get("code", "")
            ok, err = _syntax_ok(code)
            if not ok:
                return {"error": err, "code": "SYNTAX_ERROR"}
            (USER_DIR / m["filename"]).write_text(code)
            m.update({k: payload[k] for k in ("name", "description", "category") if k in payload})
            _write_manifest(man)
            git_persist([str(USER_DIR / m["filename"]), str(MANIFEST)], f"update(strategy): {m['name']}")
            try:
                # re-register: remove old then load new
                _registry.pop(f"user_{sid}", None)
                _load_one(USER_DIR / m["filename"], sid)
                m["status"] = "registered"
            except Exception as e:
                m["status"] = "error"; m["error"] = str(e)[:200]
            return m
    return {"error": "not found"}

def delete_strategy(sid: str) -> dict:
    man = _read_manifest()
    new = [m for m in man if m["id"] != sid]
    if len(new) == len(man):
        return {"error": "not found"}
    _write_manifest(new)
    f = USER_DIR / f"{sid}.py"
    if f.exists():
        f.unlink()
    _registry.pop(f"user_{sid}", None)
    git_persist([str(MANIFEST), str(f)], f"delete(strategy): {sid}")
    return {"status": "deleted"}

def _now() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat()


_ensure_registered()
