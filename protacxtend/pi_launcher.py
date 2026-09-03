"""Slice E — Pi launcher.

`PROTACXtend` (no args, on a TTY) starts the Pi-backed TUI directly when a Pi
binary and the runtime extension are available:

    PROTACXtend
      └─ protacxtend.cli → pi_launcher → pi -e runtime/src/index.ts  (pi-tui)

Developer commands (`cd runtime && npm install`, `pi -e src/index.ts`) remain
available but are not required for production use.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def extension_path() -> Path:
    return repo_root() / "runtime" / "src" / "index.ts"


def pi_binary() -> Optional[str]:
    return os.environ.get("PROTACXTEND_PI_BIN") or shutil.which("pi")


def resolve_pi_command(extra_args: Optional[List[str]] = None) -> Optional[List[str]]:
    """Return the pi argv to run the PROTACXtend TUI, or None if unavailable."""
    binary = pi_binary()
    ext = extension_path()
    if not binary:
        return None
    if not ext.exists():
        return None
    return [binary, "-e", str(ext), *(extra_args or [])]


def launch_pi(extra_args: Optional[List[str]] = None) -> int:
    """Exec the Pi TUI (replaces this process). Returns exit code on failure."""
    argv = resolve_pi_command(extra_args)
    if argv is None:
        print("Pi runtime unavailable — install pi (npm i -g @earendil-works/pi-coding-agent) "
              "and ensure runtime/src/index.ts exists.", file=sys.stderr)
        return 127
    try:
        os.chdir(repo_root())
        os.execvp(argv[0], argv)
    except FileNotFoundError:
        print(f"pi binary not found: {argv[0]}", file=sys.stderr)
        return 127
    except Exception as exc:  # exec replaces the process; errors here are rare
        print(f"could not launch pi: {exc}", file=sys.stderr)
        return 126
