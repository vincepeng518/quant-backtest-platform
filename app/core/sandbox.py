from __future__ import annotations

import ast
from typing import Tuple

# Forbidden modules / builtins for user-uploaded strategies (defense-in-depth
# against accidental RCE — solo SaaS still execs user code, this blocks the
# obvious dangerous imports).
_FORBIDDEN_MODULES = {
    "os", "sys", "subprocess", "shutil", "socket", "pickle", "cPickle",
    "ctypes", "multiprocessing", "threading", "asyncio", "pathlib",
    "builtins", "importlib", "glob", "tempfile", "requests", "urllib",
    "http", "ftplib", "smtplib", "telnetlib", "paramiko", "pty", "fcntl",
}
_FORBIDDEN_BUILTINS = {"eval", "exec", "compile", "__import__", "open"}


def check_strategy_code(code: str) -> Tuple[bool, str]:
    """Return (ok, error). Rejects code importing dangerous modules or calling
    eval/exec/__import__/open."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        return False, f"SyntaxError: {e.msg} (line {e.lineno})"

    for node in ast.walk(tree):
        # import X / import X.Y / from X import Y
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _FORBIDDEN_MODULES:
                    return False, f"Forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in _FORBIDDEN_MODULES:
                return False, f"Forbidden import: {node.module}"
        # __builtins__ access
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_BUILTINS:
                return False, f"Forbidden call: {func.id}()"
            if isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_BUILTINS:
                return False, f"Forbidden call: .{func.attr}()"
    return True, ""
