"""
Conversational agent contracts — ToolResult, DesignObjective, AgentEvent.
=======================================================================

Shared types for the PROTACXtend conversational layer. These mirror the
scientific response contract (section 8) so every tool renders the same way
in the TUI and no layer can silently blur evidence types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EvidenceType(str, Enum):
    RETRIEVED = "RETRIEVED"
    CALCULATED = "CALCULATED"
    ML_PREDICTION = "ML PREDICTION"
    STRUCTURAL_SURROGATE = "STRUCTURAL SURROGATE"
    HEURISTIC = "HEURISTIC"
    USER_INPUT = "USER INPUT"
    NOT_AVAILABLE = "NOT AVAILABLE"


class ToolStatus(str, Enum):
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ToolResult:
    tool: str
    status: ToolStatus = ToolStatus.SUCCESS
    summary: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    sources: List[str] = field(default_factory=list)
    confidence: Optional[float] = None
    model_version: Optional[str] = None
    evidence_type: EvidenceType = EvidenceType.NOT_AVAILABLE
    limitations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def compact(self, max_data: int = 1200) -> str:
        """Compact representation for the LLM context (cost control)."""
        data = str(self.data)
        if len(data) > max_data:
            data = data[:max_data] + "… (truncated)"
        return (f"[{self.tool}] {self.status.value} · {self.evidence_type.value}\n"
                f"summary: {self.summary}\ndata: {data}\n"
                f"sources: {self.sources}\nlimitations: {self.limitations}")


@dataclass
class DesignObjective:
    """Typed objective extracted by the chat layer before graph handoff."""

    task: str = "design_protac"
    target: str = ""
    e3_ligase: str = ""
    primary_objectives: List[str] = field(default_factory=list)
    secondary_objectives: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    requested_candidates: Optional[int] = None
    cell_line: Optional[str] = None
    run_id: str = ""

    def to_request_text(self) -> str:
        """Canonical objective sentence for the deterministic graph entry.

        The underlying SynGlue workflow currently parses natural-language
        requests (see backend.main.run_workflow_from_request); this sentence
        is *constructed from typed fields*, never from the raw user string.
        """
        parts = [f"Design {self.requested_candidates or ''} {'PROTAC' if not self.e3_ligase else self.e3_ligase + ' PROTAC'} candidates".strip()]
        if self.target:
            parts.append(f"for {self.target}")
        if self.cell_line:
            parts.append(f"in {self.cell_line}")
        if self.primary_objectives:
            parts.append(f"prioritizing {' and '.join(self.primary_objectives)}")
        if self.secondary_objectives:
            parts.append(f"additionally considering {' and '.join(self.secondary_objectives)}")
        if self.constraints:
            constraints = ", ".join(f"{k}: {v}" for k, v in self.constraints.items())
            parts.append(f"constraints: {constraints}")
        return " ".join(parts) + "."


@dataclass
class AgentEvent:
    """Compact, streaming, UI-safe event (never chain-of-thought)."""

    kind: str            # research | target | chemistry | structure | prediction | ranking | workflow | tool | gate | system
    action: str = ""
    tool: str = ""
    status: str = "ok"
    summary: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        head = f"[{self.kind}]"
        if self.action:
            head += f" {self.action}"
        if self.tool:
            head += f" · {self.tool}"
        if self.status != "ok":
            head += f" ({self.status})"
        line = head
        if self.summary:
            line += f" → {self.summary}"
        return line


class RegistryError(ValueError):
    """Tool name outside the strict registry or rejected parameters."""
