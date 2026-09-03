"""PROTACpilot pipeline tests: blueprint integrity + honest external blocking."""

from __future__ import annotations

import pytest

from protacxtend.workflows.protacpilot_blueprint import (
    PROTACpILOT_BLUEPRINT,
    node_names,
)


@pytest.fixture(autouse=True)
def _stub_network(monkeypatch):
    from protacxtend.agentic.contract import EvidenceType, ToolResult, ToolStatus
    monkeypatch.setattr("protacxtend.agentic.registry.exec_resolve_target",
                        lambda *a, **k: ToolResult(tool="resolve_target", summary="BRD4 → O60885",
                                                   sources=["O60885"], evidence_type=EvidenceType.RETRIEVED))
    monkeypatch.setattr("protacxtend.agentic.registry.exec_ligase_evidence",
                        lambda *a, **k: ToolResult(tool="retrieve_e3_evidence", summary="CRBN catalog row",
                                                   evidence_type=EvidenceType.RETRIEVED))


def test_blueprint_order_and_reference_order():
    names = node_names()
    assert names[0] == "research_planner"
    assert "ternary_generator" in names
    assert names.index("know_target") < names.index("protac_decomposer")
    assert names.index("ternary_generator") < names.index("md_validator")
    # reproducibility report is last
    assert names[-1] == "reproducibility_report"


def test_pipeline_executes_local_then_blocks_externals():
    from protacxtend.workflows.pilot_runner import run_protacpilot_pipeline
    events = []
    ctx = {"target": "BRD4", "e3": "CRBN", "protac_smiles": "CCO", "objective": ""}
    result = run_protacpilot_pipeline(ctx, events.append)
    assert result["blocked_at"] == "ternary_generator"
    # real steps ran before the external gate
    ran = {e["name"] for e in events if e["status"] == "success"}
    assert "know_target" in ran
    assert "know_e3" in ran
    # external engine is reported NOT AVAILABLE, never fabricated
    blocked = [e for e in events if e["name"] == "ternary_generator" and e["status"] == "blocked"]
    assert blocked and "COMPASS" in blocked[0]["summary"]
    # no downstream node claims success past the block
    past = [e for e in events
            if PROTACpILOT_BLUEPRINT and _idx(e["name"]) > _idx("ternary_generator")]
    assert all(e["status"] in ("blocked", "skipped") or e["name"].startswith("research")
               for e in past)


def _idx(name: str) -> int:
    try:
        return node_names().index(name)
    except ValueError:
        return -1


def test_no_fabricated_md_or_bor5():
    from protacxtend.workflows.pilot_runner import run_protacpilot_pipeline
    events = []
    run_protacpilot_pipeline({"target": "BRD4", "e3": "CRBN", "protac_smiles": "CCO"}, events.append)
    for name in ("md_validator", "bRo5_exposure_predictor", "pose_consensus"):
        hits = [e for e in events if e["name"] == name]
        assert hits and hits[0]["status"] in ("blocked", "skipped")
