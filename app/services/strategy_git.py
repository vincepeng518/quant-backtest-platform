from __future__ import annotations
import logging, os, subprocess
from pathlib import Path

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]
GIT_URL = "https://{token}@github.com/vincepeng518/quant-backtest-platform.git"

def _git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)

def git_persist(files: list[str], message: str) -> tuple[bool, str]:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return False, "GITHUB_TOKEN missing"
    try:
        _git(["config", "user.email", "agent@hermes.local"])
        _git(["config", "user.name", "quant-agent"])
        _git(["remote", "set-url", "origin", GIT_URL.format(token=token)])
        _git(["add", *files])
        # 若無變更，視為成功
        cp = _git(["commit", "-m", message])
        if cp.returncode != 0:
            if "nothing to commit" in cp.stdout + cp.stderr:
                return True, "no changes"
            return False, cp.stderr[:300]
        push = _git(["push", "origin", "master"])
        if push.returncode != 0:
            return False, push.stderr[:300]
        return True, "pushed"
    except Exception as e:
        return False, str(e)[:300]
