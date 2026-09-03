"""Normalized runtime event schema (shared by Pi, worker, LangGraph, tools)."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

KINDS = {"tool", "workflow", "node", "agent", "artifact", "warning", "gate"}
STATUSES = {"pending", "running", "success", "warning", "error", "cancelled"}


def normalize_event(*, kind: str, name: str, status: str = "running",
                    summary: str = "", data: Optional[Dict[str, Any]] = None,
                    session_id: str = "", run_id: str = "",
                    source_tool: Optional[str] = None,
                    source_model: Optional[str] = None,
                    source_version: Optional[str] = None,
                    evidence_type: Optional[str] = None,
                    artifact_ids=None, warnings=None, limitations=None,
                    event_id: Optional[str] = None, ts: Optional[float] = None,
                    ) -> Dict[str, Any]:
    if kind not in KINDS:
        kind = "workflow"
    if status not in STATUSES:
        status = "running"
    return {
        "event_id": event_id or f"evt-{uuid.uuid4().hex[:12]}",
        "timestamp": time.time() if ts is None else ts,
        "session_id": session_id or "",
        "run_id": run_id or "",
        "kind": kind,
        "name": name,
        "status": status,
        "summary": summary,
        "data": data or {},
        "source": {"tool": source_tool, "model": source_model, "version": source_version},
        "evidence_type": evidence_type,
        "artifact_ids": artifact_ids or [],
        "warnings": warnings or [],
        "limitations": limitations or [],
    }
