"""Project / session / run store — slice G.

Layout (root = PROTACXTEND_HOME or ~/.protacxtend):

  projects/    <project_id>.json      scientific workspace records
  sessions/    <session_id>.json      full session context (refs to artifacts)
  runs/        <run_id>.json          run records
  outputs/     <project>/<run_id>/    artifacts (slice H)
  evidence/ evidence/ cache/ environments/ models/ logs/

Sessions store *references* to artifacts rather than giant raw payloads.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from protacxtend.state.events import normalize_event


def root() -> Path:
    return Path(os.environ.get("PROTACXTEND_HOME", str(Path.home() / ".protacxtend"))).expanduser()


def ensure_dirs() -> Dict[str, Path]:
    base = root()
    dirs = {
        "projects": base / "projects",
        "sessions": base / "sessions",
        "runs": base / "runs",
        "outputs": base / "outputs",
        "evidence": base / "evidence",
        "artifacts": base / "artifacts",
        "cache": base / "cache",
        "environments": base / "environments",
        "models": base / "models",
        "logs": base / "logs",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "unnamed"


# ── projects ────────────────────────────────────────────────────────────

def create_project(name: str, notes: str = "", meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    dirs = ensure_dirs()
    project_id = _slug(name)
    now = time.time()
    record = {
        "project_id": project_id,
        "name": name,
        "created_at": now,
        "updated_at": now,
        "targets": [], "e3s": [], "cell_lines": [],
        "active_session": None,
        "run_ids": [], "artifact_ids": [], "evidence_ids": [],
        "notes": notes, "scientific_context": meta or {},
    }
    _write_json(dirs["projects"] / f"{project_id}.json", record)
    return record


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    p = ensure_dirs()["projects"] / f"{_slug(project_id)}.json"
    return _read_json(p)


def list_projects() -> List[str]:
    return sorted(p.stem for p in ensure_dirs()["projects"].glob("*.json"))


def touch_project(project_id: str, **updates: Any) -> Dict[str, Any]:
    record = get_project(project_id)
    if record is None:
        record = create_project(project_id)
    record["updated_at"] = time.time()
    for k, v in updates.items():
        if k in record:
            record[k] = v
    _write_json(ensure_dirs()["projects"] / f"{record['project_id']}.json", record)
    return record


# ── sessions ────────────────────────────────────────────────────────────

def save_session(session_id: str, project_id: str, payload: Dict[str, Any]) -> Path:
    dirs = ensure_dirs()
    safe = _slug(session_id)
    record = {"session_id": session_id, "project_id": project_id,
              "updated_at": time.time(), "context": payload}
    path = dirs["sessions"] / f"{safe}.json"
    _write_json(path, record)
    if get_project(project_id):
        touch_project(project_id, active_session=session_id)
    return path


def resume_session(session_id: str) -> Optional[Dict[str, Any]]:
    return _read_json(ensure_dirs()["sessions"] / f"{_slug(session_id)}.json")


def list_sessions() -> List[str]:
    return sorted(p.stem for p in ensure_dirs()["sessions"].glob("*.json"))


# ── runs ────────────────────────────────────────────────────────────────

def new_run(project_id: str, objective: Dict[str, Any], session_id: str = "") -> Dict[str, Any]:
    dirs = ensure_dirs()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_id = f"run-{stamp}-{os.getpid()}"
    output_dir = dirs["outputs"] / _slug(project_id) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "run_id": run_id, "project_id": _slug(project_id), "session_id": session_id,
        "objective": objective, "created_at": time.time(), "status": "running",
        "artifact_ids": [], "events_path": str(output_dir / "events.jsonl"),
    }
    _write_json(dirs["runs"] / f"{run_id}.json", record)
    touch_project(project_id, run_ids=list({*get_project(project_id)["run_ids"], run_id}))
    return record


def append_event(run: Dict[str, Any], event: Dict[str, Any]) -> None:
    path = Path(run.get("events_path") or "")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(event) + "\n")


def finish_run(run: Dict[str, Any], summary: Dict[str, Any]) -> None:
    run["status"] = "success"
    run["summary"] = summary
    run["updated_at"] = time.time()
    _write_json(ensure_dirs()["runs"] / f"{run['run_id']}.json", run)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def wipe_home_for_tests(tmp: Path) -> None:
    """Point the store at a temp dir for tests."""
    os.environ["PROTACXTEND_HOME"] = str(tmp)
