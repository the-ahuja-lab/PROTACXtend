"""Launcher tests — invocation from any cwd resolves the same absolute runtime."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _root_env(monkeypatch):
    monkeypatch.setenv("PROTACXTEND_ROOT", str(ROOT))


def test_repo_root_is_installation_anchored_not_cwd(monkeypatch):
    from protacxtend import pi_launcher as pl
    for where in [ROOT, ROOT / "CLI", ROOT / "protacxtend" / "cli.py", Path("/tmp")]:
        monkeypatch.chdir(where if where.is_dir() else where.parent)
        assert pl.repo_root() == ROOT


def test_resolve_uses_absolute_extension_from_any_cwd(monkeypatch):
    from protacxtend import pi_launcher as pl
    monkeypatch.setenv("PROTACXTEND_PI_BIN", "/bin/echo")
    for cwd in [ROOT, ROOT / "CLI", Path("/tmp")]:
        monkeypatch.chdir(cwd)
        cmd = pl.resolve_pi_command()
        assert cmd is not None
        ext = cmd[cmd.index("-e") + 1]
        assert ext == str(ROOT / "runtime" / "src" / "index.ts")   # absolute
        assert not Path(ext).is_relative_to(cwd) or cwd == ROOT


def test_package_json_and_extension_exist():
    from protacxtend import pi_launcher as pl
    assert pl.package_json().exists()
    assert pl.extension_path().exists()


def test_launch_does_not_chdir(monkeypatch, tmp_path):
    from protacxtend import pi_launcher as pl
    monkeypatch.setenv("PROTACXTEND_PI_BIN", "/bin/echo")
    launched = {}
    calls = []

    def fake_execvp(binary, argv):
        launched["binary"] = binary
        launched["cwd"] = os.getcwd()
        calls.append(argv)
    monkeypatch.setattr(pl.os, "execvp", fake_execvp)
    monkeypatch.setattr(pl, "ensure_runtime_deps", lambda *a, **k: True)
    monkeypatch.chdir(tmp_path)
    pl.launch_pi()
    assert launched.get("cwd") == str(tmp_path)          # workspace preserved
    assert calls[0][0] == "/bin/echo"
    assert str(ROOT / "runtime" / "src" / "index.ts") in calls[0]


def test_runtime_deps_missing_gives_clear_action(monkeypatch, capsys):
    from protacxtend import pi_launcher as pl
    monkeypatch.setattr(pl, "runtime_deps_ready", lambda: False)
    monkeypatch.setattr(pl, "pi_binary", lambda: "/bin/echo")
    monkeypatch.delenv("PROTACXTEND_AUTO_SETUP", raising=False)
    assert pl.launch_pi() == 3
    out = capsys.readouterr().err
    assert "npm install" in out and "runtime" in out


def test_status_command_fields(capsys):
    from protacxtend import pi_launcher as pl
    assert pl.print_runtime_status() == 0
    out = capsys.readouterr().out
    for field in ("PROTACXtend root:", "Runtime path:", "Pi executable:",
                  "Node version:", "runtime dependencies:", "Python worker:",
                  "LLM config:", "Status:"):
        assert field in out
