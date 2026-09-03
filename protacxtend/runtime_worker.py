"""
PROTACXtend runtime worker — long-lived JSONL science bridge.
===============================================================

A persistent Python process speaking JSON Lines over stdin/stdout. Pi and the
Node TUI spawn ONE worker per session and reuse it for every tool call (no
fresh interpreter per call).

Protocol (one JSON object per line):

  REQUEST   {"id": "...", "type": "ping"|"catalog"|"tool"|"workflow"|"session.*"|"shutdown",
             "tool": "...", "args": {...}, "session_id": "...", "run_id": "..."}

  RESPONSE  {"id": "...", "type": "result|error", "status": "ok|success|warning|error",
             "data": {...}, "summary": "...", "sources": [...], "warnings": [...],
             "limitations": [...], "evidence_type": "...", "tool": "..."}

Execution goes through the *same* strict registry and typed-objective paths as
the conversational agent — nothing is duplicated here.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from protacxtend.agentic.contract import DesignObjective, ToolResult
from protacxtend.agentic.registry import execute_tool, registry_specs
from protacxtend.state import artifacts as art_store
from protacxtend.state import store as state_store
from protacxtend.state.events import normalize_event

HOME_ROOT = Path(os.environ.get("PROTACXTEND_HOME", str(Path.home() / ".protacxtend")))
SESSIONS = HOME_ROOT / "sessions"
RUNS = HOME_ROOT / "runs"
SESSIONS.mkdir(parents=True, exist_ok=True)
RUNS.mkdir(parents=True, exist_ok=True)


def emit(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()


def ok(req: Dict[str, Any], **fields: Any) -> None:
    emit({"id": req.get("id"), "type": "result", "status": "ok", **fields})


def err(req: Dict[str, Any], message: str, **fields: Any) -> None:
    emit({"id": req.get("id"), "type": "error", "status": "error",
          "summary": message, **fields})


def _session_file(session_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (session_id or "default"))
    return SESSIONS / f"{safe}.jsonl"


def handle(req: Dict[str, Any]) -> None:
    kind = str(req.get("type", "")).strip()

    if kind == "ping":
        ok(req, data={"ok": True, "home": str(HOME_ROOT),
                      "python": sys.version.split()[0]})
        return

    if kind == "catalog":
        ok(req, data={"tools": registry_specs(ready_only=True)})
        return

    if kind == "tool":
        tool = str(req.get("tool", ""))
        args = req.get("args") or {}
        try:
            result: ToolResult = execute_tool(tool, args)
        except Exception as exc:  # unknown tool &c.
            err(req, f"tool execution failed · {exc}")
            return
        emit({
            "id": req.get("id"), "type": "result",
            "status": result.status.value, "tool": result.tool,
            "summary": result.summary,
            "data": result.data, "sources": result.sources,
            "warnings": result.warnings, "limitations": result.limitations,
            "evidence_type": result.evidence_type.value,
            "confidence": result.confidence, "model_version": result.model_version,
        })
        return

    if kind == "workflow":
        from protacxtend.agents.stream import stream_workflow_events_sync
        from protacxtend.backend.main import summarize_state
        obj_dict = req.get("objective") or {}
        try:
            fields = DesignObjective.__dataclass_fields__
            objective = DesignObjective(**{k: v for k, v in obj_dict.items()
                                           if k in fields and v is not None})
        except Exception as exc:
            err(req, f"invalid objective · {exc}")
            return

        project_id = str(req.get("project_id") or "").strip()
        session_id = str(req.get("session_id") or "").strip()
        run = None
        if project_id and not state_store.get_project(project_id):
            state_store.create_project(project_id)
        if project_id:
            run = state_store.new_run(project_id, objective=objective.__dict__, session_id=session_id)

        def emit_event_line(payload) -> None:
            sys.stdout.write(json.dumps(payload, default=str) + "\n")
            sys.stdout.flush()

        def stream_emit(**evt) -> None:
            event = normalize_event(**evt, session_id=session_id,
                                    run_id=(run or {}).get("run_id", ""))
            if run:
                state_store.append_event(run, event)
            emit_event_line({"id": req.get("id"), "type": "event", **event})

        try:
            state = stream_workflow_events_sync(
                objective.to_request_text(), stream_emit,
                session_id=session_id, run_id=(run or {}).get("run_id", ""))
            summary = summarize_state(state) if state is not None else {}
        except Exception as exc:
            if run:
                state_store.finish_run(run, {"error": str(exc)})
            err(req, f"workflow failed · {exc}")
            return

        artifact_ids: list = []
        if run:
            run_dir = (state_store.ensure_dirs()["outputs"] / project_id / run["run_id"])
            producer = {"tool": "workflow", "model": None, "version": "syn-glue"}
            meta = art_store.write_artifact(
                run_dir, type="objective", filename="objective.json",
                data=objective.__dict__, producer=producer,
                project_id=project_id, session_id=session_id, run_id=run["run_id"])
            artifact_ids.append(meta["artifact_id"])
            meta = art_store.write_artifact(
                run_dir, type="run", filename="run.json", data=run, producer=producer,
                project_id=project_id, session_id=session_id, run_id=run["run_id"])
            artifact_ids.append(meta["artifact_id"])
            meta = art_store.write_artifact(
                run_dir, type="summary", filename="summary.json", data=summary, producer=producer,
                project_id=project_id, session_id=session_id, run_id=run["run_id"],
                inputs=artifact_ids)
            artifact_ids.append(meta["artifact_id"])
            run["artifact_ids"] = artifact_ids
            state_store.finish_run(run, summary)

        ok(req, data={"objective": objective.__dict__,
                      "request": objective.to_request_text(),
                      "summary": summary,
                      "run_id": (run or {}).get("run_id", ""),
                      "project_id": project_id,
                      "artifact_ids": artifact_ids,
                      "artifacts_dir": str((state_store.ensure_dirs()["outputs"] / project_id / run["run_id"])
                                           if run else "")})
        return

    if kind in ("session.save", "session.resume", "session.list", "session.evidence"):
        session_id = str(req.get("session_id") or "default")
        if kind == "session.save":
            path = _session_file(session_id)
            payload = req.get("payload") or {}
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"session_id": session_id, "payload": payload}, default=str) + "\n")
            ok(req, data={"session_id": session_id, "path": str(path)})
            return
        if kind == "session.list":
            ok(req, data={"sessions": [p.stem for p in SESSIONS.glob("*.jsonl")]})
            return
        if kind == "session.resume":
            path = _session_file(session_id)
            rows = []
            if path.exists():
                for line in path.read_text().splitlines():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            ok(req, data={"session_id": session_id, "rows": rows})
            return
        ok(req, data={"sessions_dir": str(SESSIONS)})
        return

    if kind in ("project.create", "project.list", "project.get", "session_state.save",
               "session_state.resume", "session_state.list"):
        if kind == "project.create":
            record = state_store.create_project(str(req.get("name") or "project"),
                                                notes=str(req.get("notes") or ""),
                                                meta=req.get("meta") or {})
            ok(req, data=record)
            return
        if kind == "project.list":
            ok(req, data={"projects": state_store.list_projects()})
            return
        if kind == "project.get":
            record = state_store.get_project(str(req.get("project_id") or ""))
            ok(req, data=record or {"error": "not found"})
            return
        session_id = str(req.get("session_id") or "default")
        if kind == "session_state.save":
            path = state_store.save_session(session_id, str(req.get("project_id") or "default"),
                                            payload=req.get("context") or {})
            ok(req, data={"session_id": session_id, "path": str(path)})
            return
        if kind == "session_state.list":
            ok(req, data={"sessions": state_store.list_sessions()})
            return
        record = state_store.resume_session(session_id)
        ok(req, data=record or {"error": "not found"})
        return

    if kind == "run.new":
        project_id = str(req.get("project_id") or "")
        if project_id and not state_store.get_project(project_id):
            state_store.create_project(project_id)
        run = state_store.new_run(project_id, objective=req.get("objective") or {},
                                  session_id=str(req.get("session_id") or ""))
        ok(req, data=run)
        return

    if kind == "shutdown":
        emit({"id": req.get("id"), "type": "bye", "status": "ok"})
        sys.exit(0)

    err(req, f"unknown request type '{kind}'")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            emit({"id": None, "type": "error", "status": "error",
                  "summary": "invalid JSON request"})
            continue
        try:
            handle(req)
        except Exception as exc:  # never let the worker die from one request
            err(req, f"worker error · {exc}")


if __name__ == "__main__":
    main()
