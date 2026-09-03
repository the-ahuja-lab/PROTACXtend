"""PROTACpilot pipeline tests: blueprint integrity + honest external blocking."""

from __future__ import annotations

import json

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
    ctx = {"target": "BRD4", "e3": "VHL", "protac_smiles": "CCO", "objective": ""}
    result = run_protacpilot_pipeline(ctx, events.append)
    assert result["blocked_at"] == "ternary_generator"
    # real steps ran before the external gate
    ran = {e["name"] for e in events if e["status"] == "success"}
    assert "know_target" in ran
    assert "know_e3" in ran
    # PROTAC-Model backend blocked honestly: dependencies missing, nothing fabricated
    blocked = [e for e in events if e["name"] == "ternary_generator" and e["status"] == "blocked"]
    assert blocked and "PROTAC-Model" in blocked[0]["summary"]
    assert "MISSING" in blocked[0]["summary"] or "missing" in blocked[0]["summary"]
    # poses were never invented
    assert "poses" not in json.dumps(blocked[0].get("data", {}))
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


def test_conformer_success_is_mapped_to_success(monkeypatch):
    from protacxtend.workflows import pilot_runner
    monkeypatch.setattr("protacxtend.workflows.pilot_runner._run_local",
                        lambda *a, **k: None)  # avoid recursion guard (not used)
    from protacxtend.tools.chemistry_core import generate_3d_conformer as real
    # real MZ1 conformer now succeeds after maxAttempts->maxIterations fix
    mz1 = open(__import__("pathlib").Path(__file__).resolve().parents[2] /
               "data/protac_repos/repos/PROTAC-Model_benchmark/structures/5T35/protac.smi").read().strip()
    res = real(mz1, max_attempts=2000, seed=42)
    assert res.get("status") == "success" and res.get("molblock")


def test_protac_model_status_detects_missing_deps():
    from protacxtend.workflows.pilot_runner import protac_model_status
    status = protac_model_status()
    # repo is present in this checkout; heavy external binaries are NOT available
    assert status["dir"].endswith("PROTAC-Model")
    assert status["ready"] is False
    assert any(v == "MISSING" for v in status["deps"].values())


def test_derive_site_5t35_from_crystal():
    from pathlib import Path
    from protacxtend.workflows.pilot_runner import derive_site_from_crystal
    crystal = Path(__file__).resolve().parents[2] / "data/protac_repos/repos" / \
        "PROTAC-Model_benchmark" / "structures" / "5T35" / "5t35_AD.pdb"
    site = derive_site_from_crystal(crystal)
    assert site is not None
    assert isinstance(site["x"], float) and isinstance(site["y"], float)
    assert site["source"] == "derived_from_crystal_interface"


def test_blocked_response_carries_derived_site():
    from protacxtend.workflows.pilot_runner import run_protac_model
    r = run_protac_model({"target": "BRD4", "e3": "VHL"})
    assert r["status"] == "blocked"
    derived = r.get("data", {}).get("derived_site")
    assert derived is not None and derived.get("x")
    assert "requirements" in r.get("data", {})
