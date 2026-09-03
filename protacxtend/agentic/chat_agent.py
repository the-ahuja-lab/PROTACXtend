"""
PROTACXtend conversational scientific agent.
=============================================

Runs an iterative loop: model decides one of
  {tool_call, workflow_handoff, clarification, final_answer},
the action is validated against the strict registry (rejected actions are
re-prompted, never executed), approved tools run for real, observations are
appended as compact evidence, and — when the user asks for a full degrader
workflow — a typed DesignObjective is handed to the existing deterministic
SynGlue graph. The conversational layer sits ABOVE the graph; it never
replaces it, never reveals chain-of-thought, and never fabricates tool output.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from protacxtend.agentic.contract import (
    AgentEvent,
    DesignObjective,
    EvidenceType,
    RegistryError,
    ToolResult,
    ToolStatus,
)
from protacxtend.agentic.registry import (
    execute_tool,
    registry_specs,
    spec_for,
    tools_catalog_text,
)
from protacxtend.llm.json_repair import parse_json_robust
from protacxtend.llm.providers import ProviderConfig, get_config, get_provider

ACTION_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": True,
}

SYSTEM_HEAD = (
    "You are the PROTACXtend scientific agent. You sit above a deterministic degrader-design "
    "engine and speak to a computational biologist.\n"
    "Rules:\n"
    "1. Reply ONLY as a JSON object with an \"action\" key. Actions:\n"
    "   - \"tool_call\":  {\"tool\": <name>, \"params\": {...}} — only if a registered tool helps.\n"
    "   - \"workflow_handoff\": {\"objective\": {target, e3_ligase, primary_objectives, "
    "secondary_objectives, constraints, requested_candidates, cell_line}} — when the user asks for "
    "candidate design/degradaer workflows.\n"
    "   - \"clarification\": {\"question\": \"...\"} — when target/E3/cell context is ambiguous or a "
    "human gate applies.\n"
    "   - \"final_answer\": {\"answer\": \"...\", \"evidence\": [\"RETRIEVED|CALCULATED|ML PREDICTION|"
    "STRUCTURAL SURROGATE|HEURISTIC|USER INPUT|NOT AVAILABLE\", ...]}\n"
    "2. NEVER claim a tool ran unless an observation for that tool is in context.\n"
    "3. Do not convert: cooperativity feasibility → experimental alpha; ternary occupancy → DC50; "
    "surrogate → measured. Label uncertainty.\n"
    "4. Use workflow_handoff for design requests (e.g., \"Design N PROTACs for TARGET using E3\"). "
    "Do not start the full graph for a simple factual question.\n"
    "5. Human gates: if target or E3 is ambiguous, or an expensive/experimental step is requested, "
    "return clarification first.\n"
    "Examples:\n"
    "- \"What is BRD4?\" -> tool_call(resolve_target) or final_answer — NOT workflow_handoff.\n"
    "- \"Evidence for BRD4 degradation\" -> tool_call(deep_research) then final_answer.\n"
    "- \"Compare CRBN vs VHL for BRD4\" -> tool_calls(resolve_target, retrieve_e3_evidence) then final_answer.\n"
    "- \"Design 10 CRBN PROTACs for BRD4 prioritizing degradation\" -> workflow_handoff.\n"
    "- \"Predict DC50 of a known PROTAC\" -> tool_call(predict_degradation) — do not run the full graph.\n"
    "If the user did NOT explicitly ask to design/run a candidate workflow, do NOT return workflow_handoff.\n"
)

SYSTEM_TOOLS = "\nRegistered tools (use exactly these names):\n{tools}\n"

MAX_STEPS = 10


class ClarificationNeeded(Exception):
    def __init__(self, question: str, partial: Optional["AgentRun"] = None):
        self.question = question
        self.partial = partial
        super().__init__(question)


@dataclass
class AgentRun:
    events: List[AgentEvent] = field(default_factory=list)
    transcript: List[str] = field(default_factory=list)   # compact tool observations
    objective: Optional[DesignObjective] = None
    run_id: str = ""
    summary: Dict[str, Any] = field(default_factory=dict)
    steps: int = 0

    def emit(self, kind: str, action: str = "", tool: str = "", status: str = "ok",
             summary: str = "", detail: Optional[Dict[str, Any]] = None) -> None:
        self.events.append(AgentEvent(kind=kind, action=action, tool=tool,
                                      status=status, summary=summary, detail=detail or {}))


class ConversationalAgent:
    """One conversation session (may span multiple user turns for follow-ups)."""

    def __init__(self, cfg: Optional[ProviderConfig] = None, *,
                 llm_action: Optional[Callable[[str, str], Dict[str, Any]]] = None,
                 workflow_runner: Optional[Callable[[DesignObjective], Dict[str, Any]]] = None,
                 session_context: Optional[Dict[str, Any]] = None) -> None:
        self.cfg = cfg or get_config()
        self._llm_action_hook = llm_action
        self._workflow_runner = workflow_runner or self._default_workflow
        self.session_context: Dict[str, Any] = dict(session_context or {})
        self.history: List[Dict[str, str]] = []

    # ── model action (injectable for tests) ─────────────────────────────
    def _llm_action(self, system: str, user: str) -> Dict[str, Any]:
        if self._llm_action_hook is not None:
            return self._llm_action_hook(system, user)
        raw = get_provider(self.cfg.provider).chat_raw(system, user, ACTION_SCHEMA, self.cfg)
        return parse_json_robust(raw)

    # ── graph handoff ────────────────────────────────────────────────────
    def _default_workflow(self, objective: DesignObjective) -> Dict[str, Any]:
        from protacxtend.backend.main import run_workflow_from_request, summarize_state
        request = objective.to_request_text()
        state = run_workflow_from_request(request)
        return {"objective": objective, "request": request, "state": state,
                "summary": summarize_state(state)}

    # ── the loop ─────────────────────────────────────────────────────────
    def turn(self, user_text: str, ask: Optional[Callable[[str], str]] = None) -> AgentRun:
        run = AgentRun()
        run.emit("system", action="session", summary="agent turn started")
        self.history.append({"role": "user", "content": user_text})

        observations: List[str] = []
        clarification: Optional[str] = None
        for step in range(MAX_STEPS):
            run.steps = step + 1
            system = SYSTEM_HEAD + SYSTEM_TOOLS.format(tools=tools_catalog_text())
            if self.session_context:
                system += ("\nSession context (previous runs/objective — reuse it on follow-ups):\n"
                           + json.dumps(self.session_context, indent=1) + "\n")
            user_block = {
                "user_objective": user_text,
                "conversation": "\n".join(
                    f"{t['role']}: {t['content'][:1400]}" for t in self.history[-8:]),
                "tool_observations": observations[-6:],
            }
            try:
                action = self._llm_action(system, "Analyze and return your next action JSON.\n" +
                                          json.dumps(user_block))
            except Exception as exc:
                run.emit("system", action="llm_error", status="error",
                         summary=f"model unreachable · {exc}")
                if clarification:
                    break
                raise
            name = str(action.get("action", ""))

            if name == "final_answer":
                run.emit("system", action="final_answer", status="ok",
                         summary=str(action.get("answer", ""))[:200])
                answer = str(action.get("answer", ""))
                run.summary = {"kind": "answer", "answer": answer,
                               "evidence": action.get("evidence", [])}
                self.history.append({"role": "assistant", "content": answer})
                return run

            if name == "clarification":
                clarification = str(action.get("question", "Please clarify."))
                run.emit("gate", action="clarification_required", status="ok",
                         summary=clarification[:180])
                if ask is not None:
                    reply = ask(f"  {clarification}\n  → ")
                    self.history.append({"role": "user", "content": f"(clarification) {reply}"})
                    continue
                raise ClarificationNeeded(clarification, run)

            if name == "workflow_handoff":
                return self._do_handoff(run, action.get("objective") or {})

            if name == "tool_call":
                tool = str(action.get("tool", "")).strip()
                params = action.get("params") or {}
                if not tool or tool not in {s["name"] for s in registry_specs(ready_only=True)}:
                    run.emit("system", action="tool_rejected", status="error",
                             summary=f"'{tool}' is not a registered ready tool — re-prompting")
                    observations.append("REJECTED tool call for '" + tool + "' — use only registered tools.")
                    continue
                try:
                    spec_for(tool)
                except RegistryError as exc:
                    observations.append(str(exc)); continue
                run.emit("tool", action="calling", tool=tool, status="ok",
                         summary=f"params={json.dumps(params)[:160]}")
                result: ToolResult = execute_tool(tool, params)
                compact = result.compact()
                observations.append(compact)
                run.transcript.append(compact)
                run.emit("tool", action="result", tool=tool,
                         status=result.status.value, summary=result.summary[:180],
                         detail={"evidence": result.evidence_type.value,
                                 "n_sources": len(result.sources)})
                if result.status == ToolStatus.ERROR:
                    run.emit("system", action="tool_failed", status="error",
                             summary=f"{tool} failed — {result.summary[:120]} (fallback or ask user)")
                continue

            run.emit("system", action="unknown_action", status="error",
                     summary=f"model returned unknown action '{name}' — re-prompting")
            observations.append("unknown action '" + name + "' — return a valid action.")

        run.emit("system", action="max_steps", status="error", summary="step budget exhausted")
        run.summary = {"kind": "error", "error": "step budget exhausted"}
        return run

    # ── workflow handoff implementation ──────────────────────────────────
    def _do_handoff(self, run: AgentRun, obj: Dict[str, Any]) -> AgentRun:
        fields = DesignObjective.__dataclass_fields__
        objective = DesignObjective(**{
            k: v for k, v in obj.items() if k in fields and v is not None
        })
        run.objective = objective
        run.emit("workflow", action="handoff", status="ok",
                 summary="typed DesignObjective → deterministic SynGlue graph",
                 detail=objective.__dict__)
        run.emit("gate", action="workflow_launch", status="ok",
                 summary=f"running: {objective.to_request_text()[:160]}")
        try:
            result = self._workflow_runner(objective)
        except Exception as exc:
            run.emit("workflow", action="graph_error", status="error",
                     summary=f"graph run failed · {exc}")
            run.summary = {"kind": "error", "error": str(exc)}
            return run

        state = result.get("state")
        summary = result.get("summary") or {}
        run.run_id = str(getattr(state, "run_id", "") or result.get("run_id", ""))
        self._summarize_state_events(run, state, summary)
        # Remember for follow-ups
        self.session_context.update({
            "last_objective": objective.__dict__,
            "run_id": run.run_id,
            "summary_head": {k: summary.get(k) for k in list(summary)[:12]},
        })
        answer = (f"Workflow complete (run {run.run_id or 'local'}). "
                  f"Summary: {json.dumps(summary, default=str)[:600]}")
        run.summary = {"kind": "handoff", "objective": objective.__dict__,
                       "run_id": run.run_id, "summary": summary, "answer": answer}
        self.history.append({"role": "assistant", "content": answer})
        return run

    def _summarize_state_events(self, run: AgentRun, state: Any, summary: Dict[str, Any]) -> None:
        """Emit compact, honest post-run events derived from the real state."""
        top = None
        if state is not None:
            top = getattr(state, "ranking_results", None)
        n_candidates = len(top) if top else summary.get("n_candidates", 0)
        run.emit("workflow", action="complete", status="ok",
                 summary=f"graph finished · {n_candidates} ranked candidates",
                 detail={"run_id": run.run_id})
        for key in ("target", "e3_ligase", "warheads", "linkers", "candidates"):
            if summary.get(key):
                run.emit("workflow", action=key, status="ok", summary=str(summary[key])[:180])
        if run.objective:
            run.emit("ranking", action="objective", status="ok",
                     summary=" ".join(run.objective.primary_objectives) or "—")


def one_shot(user_text: str, cfg: Optional[ProviderConfig] = None, *, verbose=True,
             ask: Optional[Callable[[str], str]] = None) -> AgentRun:
    agent = ConversationalAgent(cfg)
    try:
        return agent.turn(user_text, ask=ask)
    except ClarificationNeeded as need:
        if ask is None and need.question:
            # one-shot without a live user: surface the gate as a structured result
            run = need.partial or AgentRun()
            run.emit("gate", action="clarification_required", summary=need.question)
            run.summary = {"kind": "clarification", "question": need.question}
            return run
        raise
