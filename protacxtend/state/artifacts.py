"""Artifact store with metadata + lineage — slice H.

Artifact layout (run-level):

  outputs/<project>/<run_id>/
    objective.json run.json events.jsonl evidence.jsonl sources.json
    candidates.csv predictions.csv ranking.csv warnings.json provenance.jsonl
    final_report.md  structures/ plots/ code/ notebooks/

Every artifact is registered with an id (ART-YYYYMMDD-NNNNN), a producer
(tool/agent/node/model+version), input artifact ids, source evidence ids,
parameters, a sha256 checksum and limitations — and appended to
provenance.jsonl so lineage is traversable after restart.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def artifact_id() -> str:
    return f"ART-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


def checksum_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def register(run_dir: Path, *, artifact_id: Optional[str] = None) -> Dict[str, Any]:
    """Load (or create) the run-level provenance registry."""
    path = run_dir / "provenance.jsonl"
    return {"path": path, "rows": _read_lines(path)}


def _read_lines(path: Path) -> List[Dict[str, Any]]:
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _meta(run_dir: Path, path: Path, *, type: str, filename: str, producer: Dict[str, Any],
          project_id: str = "", session_id: str = "", run_id: str = "",
          inputs: Optional[List[str]] = None, evidence_ids: Optional[List[str]] = None,
          parameters: Optional[Dict[str, Any]] = None, limitations: Optional[List[str]] = None,
          aid: Optional[str] = None) -> Dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "artifact_id": aid or artifact_id(),
        "project_id": project_id, "session_id": session_id, "run_id": run_id,
        "type": type, "path": str(path), "filename": filename,
        "created_at": time.time(), "producer": producer,
        "inputs": inputs or [], "source_evidence": evidence_ids or [],
        "parameters": parameters or {}, "checksum": checksum_sha256(path),
        "limitations": limitations or [],
    }


def _append(run_dir: Path, meta: Dict[str, Any]) -> None:
    prov = register(run_dir)
    with prov["path"].open("a") as fh:
        fh.write(json.dumps(meta) + "\n")


def write_artifact(run_dir: Path, *, type: str, filename: str, data: Any,
                   producer: Dict[str, Any], project_id: str = "", session_id: str = "",
                   run_id: str = "", inputs: Optional[List[str]] = None,
                   evidence_ids: Optional[List[str]] = None, parameters: Optional[Dict[str, Any]] = None,
                   limitations: Optional[List[str]] = None) -> Dict[str, Any]:
    """Write one artifact, register metadata, append lineage. Returns metadata."""
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / filename
    if isinstance(data, str):
        path.write_text(data)
    elif isinstance(data, (list, dict)):
        path.write_text(json.dumps(data, indent=2, default=str) + "\n")
    else:
        raise TypeError(f"unsupported artifact payload type: {type(data)}")
    meta = _meta(run_dir, path, type=type, filename=filename, producer=producer,
                 project_id=project_id, session_id=session_id, run_id=run_id,
                 inputs=inputs, evidence_ids=evidence_ids, parameters=parameters,
                 limitations=limitations)
    _append(run_dir, meta)
    return meta


def lineage_of(run_dir: Path, artifact_id: str) -> Optional[Dict[str, Any]]:
    for row in register(run_dir)["rows"]:
        if row.get("artifact_id") == artifact_id:
            return row
    return None


def run_artifacts(run_dir: Path) -> List[Dict[str, Any]]:
    return register(run_dir)["rows"]


def write_csv(run_dir: Path, filename: str, columns: List[str], rows: List[List[Any]],
              producer: Dict[str, Any], **meta: Any) -> Dict[str, Any]:
    import csv
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / filename
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        writer.writerows(rows)
    record = _meta(run_dir, path, type="table", filename=filename, producer=producer, **meta)
    _append(run_dir, record)
    return record
