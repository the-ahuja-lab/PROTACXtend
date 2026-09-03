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
        obj_dict = req.get("objective") or {}
        try:
            fields = DesignObjective.__dataclass_fields__
            objective = DesignObjective(**{k: v for k, v in obj_dict.items()
                                           if k in fields and v is not None})
        except Exception as exc:
            err(req, f"invalid objective · {exc}")
            return
        # Deterministic graph (authoritative). Runs to completion in the worker
        # for v1; live per-node streaming is the LangGraph astream slice (F).
        from protacxtend.backend.main import run_workflow_from_request, summarize_state
        try:
            state = run_workflow_from_request(objective.to_request_text())
            summary = summarize_state(state)
        except Exception as exc:
            err(req, f"workflow failed · {exc}")
            return
        ok(req, data={"objective": objective.__dict__,
                      "request": objective.to_request_text(),
                      "summary": summary})
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
