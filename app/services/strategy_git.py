from __future__ import annotations

import base64
import json
import logging
import os
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

REPO = "vincepeng518/quant-backtest-platform"
API = f"https://api.github.com/repos/{REPO}/contents"

# Use a dedicated path inside the repo for user strategies so they survive
# redeploys (Dockerfile COPYs the repo at build time, and this writes back to
# GitHub so the next build picks them up). No git CLI required in the container.
USER_PREFIX = "strategies/user"


def _headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    h = {"Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _api(path: str, method: str = "GET", data: bytes | None = None) -> dict | None:
    url = f"{API}/{path}"
    req = urllib.request.Request(url, data=data, method=method, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # file does not exist yet
        logger.warning("GitHub API %s %s -> %s", method, path, e.read().decode()[:200])
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("GitHub API %s %s failed: %s", method, path, e)
        return None


def _put(path: str, content: str, message: str) -> tuple[bool, str]:
    """Create or update a file via Contents API."""
    existing = _api(path)
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": "master",
    }
    if existing and "sha" in existing:
        payload["sha"] = existing["sha"]
    data = json.dumps(payload).encode("utf-8")
    resp = _api(path, method="PUT", data=data)
    if resp and "content" in resp:
        return True, "pushed"
    return False, "github api error"


def _delete(path: str, message: str) -> tuple[bool, str]:
    existing = _api(path)
    if not existing or "sha" not in existing:
        return True, "nothing to delete"
    payload = {"message": message, "sha": existing["sha"], "branch": "master"}
    resp = _api(path, method="DELETE", data=json.dumps(payload).encode("utf-8"))
    if resp is not None:  # 204 returns None on success
        return True, "deleted"
    return False, "github api error"


def git_persist(files: list[str], message: str) -> tuple[bool, str]:
    """Persist user strategy files to GitHub so they survive container rebuilds.

    `files` are absolute or repo-relative paths; we map them under USER_PREFIX.
    """
    if not os.environ.get("GITHUB_TOKEN"):
        return False, "GITHUB_TOKEN missing"
    try:
        ok_all = True
        detail_parts = []
        for f in files:
            p = str(f)
            # map repo path -> github path
            if USER_PREFIX in p:
                rel = p[p.index(USER_PREFIX):]
            elif "strategies/user" in p:
                rel = "strategies/user/" + p.split("strategies/user/")[-1]
            else:
                rel = os.path.basename(p)
            if not os.path.exists(p):
                # file was deleted locally (e.g. strategy removal)
                ok, d = _delete(rel, message)
            else:
                with open(p, "r", encoding="utf-8") as fh:
                    content = fh.read()
                ok, d = _put(rel, content, message)
            ok_all = ok_all and ok
            detail_parts.append(f"{rel}:{d}")
        return ok_all, "; ".join(detail_parts)
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:300]
