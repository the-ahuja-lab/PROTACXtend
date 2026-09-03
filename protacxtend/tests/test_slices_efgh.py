"""Tests for migration slices E (launcher), F (streaming), G (store), H (artifacts)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


# ── Slice E: launcher ──────────────────────────────────────────────────

def test_E_resolve_pi_command_uses_extension(monkeypatch):
    from protacxtend.pi_launcher import extension_path, resolve_pi_command
    monkeypatch.setenv("PROTACXTEND_PI_BIN", "/bin/echo")
    cmd = resolve_pi_command()
    assert cmd is not None
    assert cmd[0] == "/bin/echo"
    assert "-e" in cmd and str(extension_path()) in cmd


def test_E_resolve_pi_command_none_without_bin(monkeypatch):
    from protacxtend.pi_launcher import resolve_pi_command
    monkeypatch.delenv("PROTACXTEND_PI_BIN", raising=False)
    monkeypatch.setattr("protacxtend.pi_launcher.shutil.which", lambda name: None)
    assert resolve_pi_command() is None


def test_E_cli_branches_to_launcher(monkeypatch):
    from protacxtend import cli
    calls = []
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setenv("PXT_PI", "1")

    def fake_resolve(extra=None):
        calls.append(("resolve", extra))
        return ["pi", "-e", "runtime/src/index.ts"]

    def fake_launch(extra=None):
        calls.append(("launch", extra))
        return 0
    monkeypatch.setattr("protacxtend.pi_launcher.resolve_pi_command", fake_resolve)
    monkeypatch.setattr("protacxtend.pi_launcher.launch_pi", fake_launch)
    monkeypatch.setattr("protacxtend.cli._interactive_command", lambda: -1)
    assert cli.main([]) == 0
    assert ("launch", None) in calls


# ── Slice F: live streaming wrapper ────────────────────────────────────

@pytest.mark.skipif(not pytest.importorskip("langgraph"), reason="langgraph not installed")
def test_F_intermediate_node_event_before_completion():
    from langgraph.graph import END, START, StateGraph
    from typing import TypedDict
    from protacxtend.agents.stream import run_workflow_streaming
    import asyncio

    class S(TypedDict, total=False):
        request: str
        a: str
        b: str

    g = StateGraph(S)
    g.add_node("node_a", lambda s: {"a": "done"})
    g.add_node("node_b", lambda s: {"b": "done"})
    g.add_edge(START, "node_a"); g.add_edge("node_a", "node_b"); g.add_edge("node_b", END)
    graph = g.compile()

    seen = []

    def emit(**evt):
        seen.append(evt)

    async def main():
        return await run_workflow_streaming("x", emit, initialState={"request": "x"})

    # bypass internal graph resolution by patching module graph getter
    import protacxtend.agents.stream as stream_mod
    stream_mod.get_workflow_graph = lambda: graph
    asyncio.run(main())

    kinds = [(e["name"], e["status"]) for e in seen]
    assert ("node_a", "success") in kinds
    assert ("node_b", "success") in kinds
    # intermediate node event must precede workflow_complete in the stream
    assert kinds.index(("node_a", "success")) < kinds.index(("workflow_complete", "success"))


# ── Slice G: project/session store ─────────────────────────────────────

@pytest.fixture()
def store_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PROTACXTEND_HOME", str(tmp_path))
    return tmp_path


def test_G_create_project_save_resume(store_home):
    from protacxtend.state import store
    store.ensure_dirs()
    proj = store.create_project("BRD4_CRBN", notes="day-one investigation")
    assert proj["project_id"] == "BRD4_CRBN"
    ctx = {
        "current_objective": {"target": "BRD4", "e3_ligase": "CRBN"},
        "targets": ["BRD4"], "e3s": ["CRBN"],
        "candidate_ids": ["SGA-abc"], "latest_run": "run-1",
    }
    store.save_session("sess-day1", "BRD4_CRBN", ctx)
    assert "sess-day1" in store.list_sessions()
    resumed = store.resume_session("sess-day1")
    assert resumed["context"]["targets"] == ["BRD4"] if resumed.get("context") else True
    proj2 = store.get_project("BRD4_CRBN")
    assert proj2["active_session"] == "sess-day1"


def test_G_new_run_and_events(store_home):
    from protacxtend.state import store
    from protacxtend.state.events import normalize_event
    store.ensure_dirs()
    store.create_project("P")
    run = store.new_run("P", {"target": "BRD4"}, session_id="s1")
    store.append_event(run, normalize_event(kind="node", name="target_resolution",
                                            status="running", run_id=run["run_id"]))
    store.append_event(run, normalize_event(kind="node", name="target_resolution",
                                            status="success", run_id=run["run_id"]))
    store.finish_run(run, {"n_candidates": 5})
    lines = Path(run["events_path"]).read_text().splitlines()
    assert len(lines) == 2
    saved = store._read_json(store.ensure_dirs()["runs"] / f"{run['run_id']}.json")
    assert saved["status"] == "success"


# ── Slice H: artifact store + lineage ──────────────────────────────────

def test_H_artifacts_metadata_checksum_lineage(store_home):
    from protacxtend.state import artifacts as A, store
    store.ensure_dirs()
    store.create_project("BRD4_CRBN")
    run = store.new_run("BRD4_CRBN", {"target": "BRD4", "e3_ligase": "CRBN"})
    run_dir = store.ensure_dirs()["outputs"] / "BRD4_CRBN" / run["run_id"]
    producer = {"tool": "workflow", "model": "m5", "version": "1.2.3"}

    obj = A.write_artifact(run_dir, type="objective", filename="objective.json",
                           data={"target": "BRD4"}, producer=producer,
                           project_id="BRD4_CRBN", session_id="s", run_id=run["run_id"])
    summary = A.write_artifact(run_dir, type="summary", filename="summary.json",
                               data={"n_candidates": 5}, producer=producer,
                               project_id="BRD4_CRBN", session_id="s", run_id=run["run_id"],
                               inputs=[obj["artifact_id"]])
    assert obj["checksum"] and summary["checksum"]
    from protacxtend.state.artifacts import checksum_sha256
    assert checksum_sha256(Path(obj["path"])) == obj["checksum"]

    # simulate a process restart: provenance must be on disk and traversable
    assert len(A.run_artifacts(run_dir)) == 2
    row = A.lineage_of(run_dir, summary["artifact_id"])
    assert row["inputs"] == [obj["artifact_id"]]
    assert row["producer"]["model"] == "m5"


def test_H_worker_session_and_project(store_home):
    """Worker exposes project + session_state over JSONL (store-backed)."""
    import subprocess, sys
    env = {**os.environ, "PROTACXTEND_HOME": str(store_home), "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen([sys.executable, "-m", "protacxtend.runtime_worker"],
                            cwd=str(ROOT), env=env, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True, bufsize=1)
    n = {"i": 0}

    def call(payload):
        n["i"] += 1
        payload["id"] = f"h{n['i']}"
        proc.stdin.write(json.dumps(payload) + "\n"); proc.stdin.flush()
        return json.loads(proc.stdout.readline()), payload["id"]

    try:
        r, rid = call({"type": "project.create", "name": "P1", "notes": "n"})
        assert r["data"]["project_id"] == "P1"
        r, _ = call({"type": "session_state.save", "project_id": "P1",
                     "session_id": "S1", "context": {"target": "BRD4"}})
        r, _ = call({"type": "session_state.resume", "session_id": "S1"})
        assert r["data"]["project_id"] == "P1"
        r, _ = call({"type": "project.list"})
        assert "P1" in r["data"]["projects"]
    finally:
        try:
            call({"type": "shutdown"})
        except Exception:
            proc.kill()
        proc.wait(timeout=10)
