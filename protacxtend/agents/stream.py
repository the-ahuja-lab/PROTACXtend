"""True LangGraph live streaming (slice F).

Runs the governed workflow with LangGraph's async `astream` in
`['updates', 'values']` mode: node labels come from `updates`, and the final
typed state comes from the last `values` snapshot — so events are real runtime
state, never timers. When LangGraph is not installed we fall back to the local
deterministic runner and emit one honest workflow event.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional

from protacxtend.agents.graph import get_workflow_graph
from protacxtend.state.events import normalize_event

Emit = Callable[..., Any]

# node -> human label
_STAGE_LABELS: Dict[str, str] = {
    "resolve_target": "target_resolution",
    "retrieve_target_binders": "warhead_binder_evidence",
    "select_e3_ligand": "e3_selection",
    "detect_exit_vectors": "exit_vector_detection",
    "generate_linkers": "linker_generation",
    "construct_candidates": "molecular_assembly",
    "validate_candidates": "candidate_validation",
    "predict_degradation": "degradation_prediction",
    "predict_admet": "admet",
    "predict_ternary": "ternary_feasibility",
    "score_ubiquitination": "lysine_ubiquitination",
    "rank_candidates": "pareto_ranking",
    "optional_ternary_feasibility": "ternary_feasibility",
    "reflect": "critic_review",
    "report": "report",
}


def _summarize_delta(delta: Dict[str, Any], node: str) -> str:
    counts = []
    for key in ("valid_candidates", "ranking_results", "degradation_predictions",
                "linkers", "retrieved_binders", "retrieved_e3_ligands"):
        val = delta.get(key)
        if isinstance(val, list):
            counts.append(f"{key}={len(val)}")
    return node if not counts else f"{node} · {' '.join(counts)}"


async def run_workflow_streaming(
    user_request: str,
    emit: Emit,
    *,
    session_id: str = "",
    run_id: str = "",
    initialState: Optional[Any] = None,
) -> Any:
    """Run the workflow, emitting node-level events as they happen."""
    emit(kind="workflow", name="workflow_start", status="running",
         summary="governed workflow started", session_id=session_id, run_id=run_id)
    graph = get_workflow_graph()
    state0 = initialState
    if state0 is None:
        from protacxtend.backend.schemas import WorkflowState
        state0 = WorkflowState(user_request=user_request)

    has_langgraph = hasattr(graph, "astream") and hasattr(graph, "invoke")
    if not has_langgraph:
        emit(kind="workflow", name="workflow_start", status="warning",
             summary="LangGraph unavailable — running local deterministic graph",
             session_id=session_id, run_id=run_id)
        final = graph.run(user_request) if hasattr(graph, "run") else graph.invoke(state0)
        emit(kind="workflow", name="workflow_complete", status="success",
             summary="local workflow finished", session_id=session_id, run_id=run_id)
        return final

    # LangGraph: astream in ["updates", "values"] mode yields (mode, payload).
    async for mode, payload in graph.astream(state0, stream_mode=["updates", "values"]):
        if mode == "updates":
            for node, delta in payload.items():
                label = _STAGE_LABELS.get(node, node)
                counts = {}
                if isinstance(delta, dict):
                    counts = {k: len(v) for k, v in delta.items() if isinstance(v, list)}
                emit(kind="node", name=label, status="success",
                     summary=_summarize_delta(delta or {}, node),
                     data={"node": node, **counts},
                     session_id=session_id, run_id=run_id)
        elif mode == "values":
            final = payload

    emit(kind="workflow", name="workflow_complete", status="success",
         summary="governed workflow finished", session_id=session_id, run_id=run_id)
    return final


def stream_workflow_events_sync(
    user_request: str,
    emit: Emit,
    *,
    session_id: str = "",
    run_id: str = "",
    initialState: Optional[Any] = None,
) -> Any:
    """Sync entrypoint for the worker/CLI (asyncio.run wrapper)."""
    return asyncio.run(run_workflow_streaming(user_request, emit, session_id=session_id,
                                              run_id=run_id, initialState=initialState))
