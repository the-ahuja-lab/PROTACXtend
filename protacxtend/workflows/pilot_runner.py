"""PROTACpilot structural workflow runner.

Executes the blueprint in order. Every step emits a normalized event. Real
local capabilities execute for real (resolve_target, retrieve_e3_evidence,
inspect_smiles, RDKit decomposition/conformers when SMILES input exists,
cooperativity/lysine where structure engines are configured). External engine
nodes (COMPASS/PRosettaC/PROTAC-Model, MD, bRo5, …) are BLOCKED with an honest
NOT AVAILABLE event — they are never simulated, and downstream structure-only
nodes are skipped with a clear explanation.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from protacxtend.workflows.protacpilot_blueprint import PROTACpILOT_BLUEPRINT


def _run_local(node: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a local blueprint step via real PROTACXtend tools."""
    engine = node.get("engine")
    from protacxtend.agentic.contract import ToolResult
    from protacxtend.agentic.registry import execute_tool

    if engine == "planner":
        return {"status": "success", "summary": f"planned objective for {ctx.get('target') or '?'}"}
    if engine == "resolve_target":
        r: ToolResult = execute_tool("resolve_target", {"target_name": ctx.get("target", "")})
        return {"status": r.status.value, "summary": r.summary, "data": r.data}
    if engine == "retrieve_e3_evidence":
        r = execute_tool("retrieve_e3_evidence", {"e3": ctx.get("e3", "CRBN")})
        return {"status": r.status.value, "summary": r.summary, "data": r.data}
    if engine == "inspect_smiles":
        smiles = ctx.get("protac_smiles") or ctx.get("smiles")
        if not smiles:
            return {"status": "blocked", "summary": "no PROTAC/Warhead SMILES provided (USER INPUT required)"}
        r = execute_tool("inspect_smiles", {"smiles": smiles})
        return {"status": r.status.value, "summary": r.summary, "data": r.data}
    if engine == "retrieve_alphafold":
        from protacxtend.tools.alphafold_client import retrieve_alphafold_id
        try:
            aid = retrieve_alphafold_id(ctx.get("target", ""))
            return {"status": "success" if aid else "blocked",
                    "summary": f"AlphaFold id: {aid}" if aid else "no AlphaFold id available",
                    "data": {"alphafold_id": aid}}
        except Exception as exc:
            return {"status": "blocked", "summary": f"alphafold lookup unavailable · {exc}"}
    if engine == "decompose_brics":
        from protacxtend.tools.brics_recap_engine import generate_brics_fragments
        smiles = ctx.get("protac_smiles")
        if not smiles:
            return {"status": "blocked", "summary": "no PROTAC SMILES to decompose"}
        frags = generate_brics_fragments(smiles)
        return {"status": "success" if frags else "warning",
                "summary": f"BRICS decomposition → {len(frags)} fragments",
                "data": {"fragments": frags[:20]}}
    if engine == "inspect_smiles_multi":
        from protacxtend.agentic.contract import EvidenceType, ToolStatus
        from protacxtend.agentic.registry import execute_tool as ex
        smiles = ctx.get("protac_smiles")
        frags = ctx.get("_fragments") or ([smiles] if smiles else [])
        ok, bad = 0, 0
        for s in frags[:20]:
            r = ex("inspect_smiles", {"smiles": s})
            if r.status == ToolStatus.SUCCESS:
                ok += 1
            else:
                bad += 1
        return {"status": "success" if ok else "warning",
                "summary": f"{ok}/{ok + bad} components valid",
                "data": {"valid": ok, "invalid": bad}}
    if engine == "conformer_3d":
        from protacxtend.tools.chemistry_core import generate_3d_conformer
        smiles = ctx.get("protac_smiles")
        if not smiles:
            return {"status": "blocked", "summary": "no SMILES for conformer generation"}
        res = generate_3d_conformer(smiles, max_attempts=50)
        return {"status": "success" if res.get("ok") or res.get("success") else "warning",
                "summary": "3D conformer generated" if res.get("ok") or res.get("success")
                else "conformer generation warning", "data": res}
    if engine == "predict_cooperativity":
        from protacxtend.tools.cooperativity_alpha_tool import run_cooperativity_predictor
        try:
            out = run_cooperativity_predictor({"target": ctx.get("target", ""),
                                               "e3": ctx.get("e3", "")})
            return {"status": "success", "summary": "cooperativity feasibility (surrogate)",
                    "data": out}
        except Exception as exc:
            return {"status": "blocked", "summary": f"cooperativity unavailable · {exc}"}
    if engine == "lysine_ubiquitination":
        return {"status": "blocked",
                "summary": "lysine proximity requires a ternary pose from a configured ternary engine"}
    return {"status": "blocked", "summary": f"no local implementation for '{engine}'"}


def run_protacpilot_pipeline(
    ctx: Dict[str, Any],
    emit: Callable[[Dict[str, Any]], None],
    blueprint: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Stream each blueprint node; stop structure-dependents at the first block."""
    nodes = blueprint or PROTACpILOT_BLUEPRINT
    results: List[Dict[str, Any]] = []
    blocked_at: Optional[str] = None
    downstream_depends_on_blocked = False

    def node_emit(node: Dict[str, Any], status: str, summary: str, data: Any = None) -> None:
        emit({"kind": "node", "name": node["node"], "stage": node["stage"], "status": status,
              "summary": summary, "evidence": node.get("evidence"), "data": data or {}})

    node_emit({"node": "research_planner", "stage": "plan"}, "running",
              f"PROTACpilot structural pipeline · objective: {json.dumps(ctx)[:160]}")
    for node in nodes:
        if node["node"] == "research_planner":
            continue
        if blocked_at is not None:
            if node.get("engine") is None or node["stage"] in (
                    "ternary", "dynamics", "prediction"):
                downstream_depends_on_blocked = True
                node_emit(node, "skipped",
                          f"skipped — depends on blocked '{blocked_at}'")
            continue
        node_emit(node, "running", node["desc"])
        if node.get("engine"):
            try:
                res = _run_local(node, ctx)
            except Exception as exc:  # pragma: no cover - defensive
                res = {"status": "error", "summary": f"step error · {exc}"}
            results.append({"node": node["node"], **res})
            node_emit(node, res["status"], res["summary"], res.get("data"))
            if res["status"] == "blocked":
                blocked_at = node["node"]
        else:
            externals = ", ".join(node.get("external") or ["external engine"])
            blocked_at = node["node"]
            node_emit(node, "blocked",
                      f"external engine required: {externals} — not configured; "
                      f"no result fabricated (NOT AVAILABLE)")
            results.append({"node": node["node"], "status": "blocked",
                            "external": externals})

    terminal = "complete"
    if blocked_at:
        terminal = f"blocked at '{blocked_at}'"
    node_emit({"node": "research_planner", "stage": "plan"}, terminal,
              f"pipeline {terminal}" + (" — downstream structure steps skipped" if downstream_depends_on_blocked else ""))
    return {"status": terminal, "results": results, "blocked_at": blocked_at}
