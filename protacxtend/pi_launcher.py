"""Slice E (final) — PROTACXtend Pi launcher.

Rules:
1. Resolve the PROTACXtend installation root FIRST (never from the caller's
   cwd): env `PROTACXTEND_ROOT` wins, then walk up from this module's own
   location until a directory that contains both `protacxtend/__init__.py`
   and `runtime/package.json` is found.
2. Build an ABSOLUTE path to <root>/runtime/src/index.ts.
3. Verify runtime/package.json + src/index.ts; ensure runtime deps are
   installed (auto-install with PROTACXTEND_AUTO_SETUP=1) or print a clear
   setup action.
4. Launch `pi -e <absolute extension>`.
5. Keep the caller's working directory as the Pi workspace — never chdir.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional


def _env_root() -> Optional[Path]:
    raw = os.environ.get("PROTACXTEND_ROOT", "").strip()
    return Path(raw).expanduser() if raw else None


def repo_root() -> Path:
    """Installation/repository root, independent of the user's cwd."""
    override = _env_root()
    if override is not None and (override / "runtime" / "package.json").exists():
        return override
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "protacxtend" / "__init__.py").exists() and \
           (candidate / "runtime" / "package.json").exists():
            return candidate
    raise RuntimeError(
        "Could not locate the PROTACXtend installation root. Set PROTACXTEND_ROOT.")


def package_json() -> Optional[Path]:
    return repo_root() / "runtime" / "package.json"


def extension_path() -> Path:
    return repo_root() / "runtime" / "src" / "index.ts"


def pi_binary() -> Optional[str]:
    return os.environ.get("PROTACXTEND_PI_BIN") or shutil.which("pi")


def runtime_deps_ready() -> bool:
    nm = repo_root() / "runtime" / "node_modules"
    return (nm / "@earendil-works" / "pi-coding-agent").exists()


def ensure_runtime_deps(verbose=True) -> bool:
    """Install runtime npm deps if missing (or auto with PROTACXTEND_AUTO_SETUP=1)."""
    if runtime_deps_ready():
        return True
    auto = os.environ.get("PROTACXTEND_AUTO_SETUP", "0") == "1"
    if auto:
        if verbose:
            print("Installing runtime dependencies (PROTACXTEND_AUTO_SETUP=1) …")
        res = subprocess.run(["npm", "install", "--no-audit", "--no-fund"],
                             cwd=str(repo_root() / "runtime"))
        if res.returncode == 0 and runtime_deps_ready():
            return True
        print("npm install failed — see output above.", file=sys.stderr)
        return False
    print(f"Runtime dependencies are missing. Run:\n"
          f"  cd {repo_root() / 'runtime'}\n  npm install\n"
          f"(or re-run with PROTACXTEND_AUTO_SETUP=1)", file=sys.stderr)
    return False


def runtime_status() -> Dict[str, object]:
    """Gather everything printed by `PROTACXtend runtime status`."""
    try:
        root = repo_root()
    except RuntimeError as exc:
        root = None
    node = subprocess.run(["node", "--version"], capture_output=True, text=True)
    pi = pi_binary()
    pi_version = ""
    if pi:
        ver = subprocess.run([pi, "--version"], capture_output=True, text=True)
        pi_version = (ver.stdout or ver.stderr).strip()
    worker_ok = True
    try:
        import protacxtend.runtime_worker  # noqa: F401
    except Exception:
        worker_ok = False
    llm_cfg = ""
    try:
        cfg_path = Path(os.environ.get("PROTACXTEND_HOME",
                                       str(Path.home() / ".protacxtend"))) / "llm.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text())
            llm_cfg = f"{cfg.get('provider')} · {cfg.get('model')} ({cfg_path})"
        else:
            llm_cfg = "not configured (run: protacxtend llm setup)"
    except Exception as exc:
        llm_cfg = f"error: {exc}"
    return {
        "root": str(root) if root else "NOT FOUND",
        "runtime_path": str(extension_path()) if root else "",
        "pi_executable": pi or "NOT FOUND",
        "node_version": (node.stdout or "").strip() or (node.stderr or "").strip(),
        "pi_version": pi_version,
        "runtime_dependencies": "ready" if (root and runtime_deps_ready()) else "MISSING",
        "python_worker": "importable" if worker_ok else "IMPORT ERROR",
        "llm_config": llm_cfg,
    }


def print_runtime_status() -> int:
    st = runtime_status()
    print("PROTACXtend root:", st["root"])
    print("Runtime path:   ", st["runtime_path"])
    print("Pi executable:  ", st["pi_executable"])
    print("Node version:   ", st["node_version"])
    print("runtime dependencies:", st["runtime_dependencies"])
    print("Python worker:  ", st["python_worker"])
    print("LLM config:     ", st["llm_config"])
    missing = (st["root"] == "NOT FOUND" or st["runtime_dependencies"] == "MISSING"
               or st["pi_executable"] == "NOT FOUND")
    print("Status:         ", "NOT READY — see above" if missing else "READY")
    return 0 if not missing else 1


def resolve_pi_command(extra_args: Optional[List[str]] = None) -> Optional[List[str]]:
    """Absolute pi argv for the PROTACXtend TUI, or None with a reason on stderr."""
    try:
        ext = extension_path()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return None
    binary = pi_binary()
    if binary is None:
        print("Pi executable not found. Install: npm i -g @earendil-works/pi-coding-agent",
              file=sys.stderr)
        return None
    if not ext.exists():
        print(f"Runtime extension missing: {ext}", file=sys.stderr)
        return None
    return [binary, "-e", str(ext), *(extra_args or [])]


def launch_pi(extra_args: Optional[List[str]] = None) -> int:
    """Launch Pi in the USER'S cwd (workspace) with the absolute extension path."""
    argv = resolve_pi_command(extra_args)
    if argv is None:
        return 127
    if not ensure_runtime_deps():
        return 3
    try:
        os.environ["PROTACXTEND_ROOT"] = str(repo_root())
        os.execvp(argv[0], argv)   # cwd intentionally untouched
    except FileNotFoundError:
        print(f"pi binary not found: {argv[0]}", file=sys.stderr)
        return 127
    except Exception as exc:
        print(f"could not launch pi: {exc}", file=sys.stderr)
        return 126
