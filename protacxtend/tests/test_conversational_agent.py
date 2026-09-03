"""
Conversational agent tests (A–H of the spec, using a scripted model).

Network adapters and the graph are stubbed here; the loop, registry
validation, gating, handoff typing and session memory are exercised for real.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from protacxtend.agentic.chat_agent import (
    ClarificationNeeded,
    ConversationalAgent,
)
from protacxtend.agentic.contract import EvidenceType, ToolResult, ToolStatus
from protacxtend.agentic.registry import execute_tool


def fake_result(tool: str, status=ToolStatus.SUCCESS, summary="ok") -> ToolResult:
    return ToolResult(tool=tool, status=status, summary=summary,
                      data={"results": [{"id": "x1"}]}, sources=["SRC:1"],
                      evidence_type=EvidenceType.RETRIEVED)


def make_agent(actions, runner=None):
    seq = list(actions)

    def llm_action(system, user):
        return seq.pop(0) if seq else {"action": "final_answer", "answer": "done."}

    def default_runner(obj):
        return {"state": SimpleNamespace(run_id="run-test", ranking_results=[{}] * 3),
                "summary": {"n_candidates": 3, "target": obj.target}}

    return ConversationalAgent(
        llm_action=llm_action, workflow_runner=runner or default_runner)


@pytest.fixture(autouse=True)
def _patch_network(monkeypatch):
    def noop_exec(name, params):
        return fake_result(name)
    monkeypatch.setattr("protacxtend.agentic.registry.exec_europe_pmc",
                        lambda *a, **k: fake_result("search_europe_pmc"))
    monkeypatch.setattr("protacxtend.agentic.registry.exec_pubmed",
                        lambda *a, **k: fake_result("search_pubmed"))
    monkeypatch.setattr("protacxtend.agentic.registry.exec_resolve_target",
                        lambda *a, **k: fake_result("resolve_target"))
    monkeypatch.setattr("protacxtend.agentic.registry.exec_crossref",
                        lambda *a, **k: fake_result("verify_crossref"))
    monkeypatch.setattr("protacxtend.agentic.registry.exec_chembl_molecules",
                        lambda *a, **k: fake_result("search_chembl"))
    monkeypatch.setattr("protacxtend.agentic.registry.exec_validate_smiles",
                        lambda *a, **k: fake_result("inspect_smiles"))


def test_A_factual_uses_tools_no_graph():
    agent = make_agent([
        {"action": "tool_call", "tool": "resolve_target", "params": {"target_name": "BRD4"}},
        {"action": "tool_call", "tool": "deep_research", "params": {"query": "BRD4 PROTAC"}},
        {"action": "final_answer", "answer": "BRD4 is a BET bromodomain target.",
         "evidence": ["RETRIEVED"]},
    ])
    run = agent.turn("What is BRD4?")
    assert run.summary["kind"] == "answer"
    assert not [e for e in run.events if e.kind == "workflow"]
    assert sum(1 for e in run.events if e.kind == "tool") >= 4  # call+result x2


def test_B_compare_uses_multiple_tools():
    agent = make_agent([
        {"action": "tool_call", "tool": "resolve_target", "params": {"target_name": "BRD4"}},
        {"action": "tool_call", "tool": "retrieve_e3_evidence", "params": {"e3": "CRBN"}},
        {"action": "tool_call", "tool": "retrieve_e3_evidence", "params": {"e3": "VHL"}},
        {"action": "final_answer", "answer": "CRBN vs VHL comparison", "evidence": ["RETRIEVED"]},
    ])
    run = agent.turn("Compare CRBN and VHL recruitment for BRD4.")
    tools = {e.tool for e in run.events if e.kind == "tool"}
    assert "retrieve_e3_evidence" in tools
    assert run.summary["kind"] == "answer"


def test_C_design_handoff_typed_objective():
    captured = {}

    def runner(obj):
        captured["obj"] = obj
        return {"state": SimpleNamespace(run_id="run-1", ranking_results=[{}] * 5),
                "summary": {"n_candidates": 5}}

    agent = make_agent([{"action": "workflow_handoff", "objective": {
        "target": "BRD4", "e3_ligase": "CRBN",
        "primary_objectives": ["degradation"],
        "secondary_objectives": ["permeability"],
        "requested_candidates": 10,
    }}], runner=runner)
    run = agent.turn("Design 10 CRBN PROTACs for BRD4 prioritizing degradation and permeability.")
    assert run.summary["kind"] == "handoff"
    obj = captured["obj"]
    assert obj.target == "BRD4" and obj.e3_ligase == "CRBN"
    assert "degradation" in obj.primary_objectives
    text = obj.to_request_text()
    assert "BRD4" in text and "CRBN" in text and "degradation" in text
    assert agent.session_context.get("last_objective", {}).get("target") == "BRD4"
    assert agent.session_context.get("run_id") == "run-1"


def test_D_followup_reuses_state_and_modifies_objective():
    def runner(obj):
        rid = "run-2" if obj.constraints.get("solubility_weight") else "run-1"
        return {"state": SimpleNamespace(run_id=rid, ranking_results=[{}] * 3),
                "summary": {"n_candidates": 3}}

    agent = make_agent([
        {"action": "workflow_handoff", "objective": {"target": "BRD4", "e3_ligase": "CRBN",
                                                     "primary_objectives": ["degradation"]}},
        {"action": "workflow_handoff", "objective": {"target": "BRD4", "e3_ligase": "CRBN",
                                                     "primary_objectives": ["degradation"],
                                                     "constraints": {"solubility_weight": 2.0}}},
    ], runner=runner)
    agent.turn("Design CRBN PROTACs for BRD4.")
    assert agent.session_context["run_id"] == "run-1"
    agent.turn("Now prioritize solubility more strongly.")
    # session memory must have carried the typed objective (no repetition needed)
    assert agent.session_context["last_objective"]["target"] == "BRD4"
    assert agent.session_context["run_id"] == "run-2"


def test_E_tool_failure_is_visible(monkeypatch):
    monkeypatch.setattr("protacxtend.agentic.registry.exec_pubmed",
                        lambda *a, **k: ToolResult(
                            tool="search_pubmed", status=ToolStatus.ERROR,
                            summary="HTTP 429 — rate limited", evidence_type=EvidenceType.RETRIEVED))
    agent = make_agent([
        {"action": "tool_call", "tool": "search_pubmed", "params": {"query": "BRD4"}},
        {"action": "final_answer", "answer": "Noted; EPMC remains available.",
         "evidence": ["RETRIEVED"]},
    ])
    run = agent.turn("Search PubMed for BRD4 PROTAC evidence.")
    assert any(e.status == "error" for e in run.events)
    assert any("HTTP 429" in e.summary for e in run.events)


def test_F_unsupported_tool_hallucination_rejected():
    agent = make_agent([
        {"action": "tool_call", "tool": "definitely_not_a_tool", "params": {}},
        {"action": "tool_call", "tool": "predict_degradation", "params": {}},  # planned → rejected
        {"action": "final_answer", "answer": "Only registered ready tools run.", "evidence": []},
    ])
    run = agent.turn("Do something impossible.")
    rejected = [e for e in run.events if e.action == "tool_rejected"]
    assert len(rejected) == 2
    assert not [e for e in run.events if e.kind == "tool" and e.action == "result"]


def test_G_human_gate_clarification():
    agent = make_agent([{"action": "clarification", "question": "BRD4 or BRD2?"}])
    with pytest.raises(ClarificationNeeded) as err:
        agent.turn("Design PROTACs for BRD.")
    assert "BRD4 or BRD2?" in err.value.question


def test_H_shared_config_file(monkeypatch, tmp_path):
    from protacxtend.llm import providers
    import protacxtend.llm.providers as prov

    monkeypatch.setenv("PROTACXTEND_HOME", str(tmp_path))
    prov.USER_CONFIG_PATH = tmp_path / "llm.json"
    prov.USER_CONFIG_PATH.write_text(
        '{"provider": "ollama", "model": "llama3.1:8b", "base_url": "http://127.0.0.1:11434"}')
    prov.reset_runtime_config()
    monkeypatch.delenv("PROTACPILOT_LLM_PROVIDER", raising=False)
    cfg = prov.get_config()
    assert cfg.provider == "ollama"
    assert cfg.model == "llama3.1:8b"


def test_strict_registry_only_ready_tools_advertised():
    from protacxtend.agentic.registry import registry_specs, spec_for
    specs = registry_specs(ready_only=True)
    names = {s["name"] for s in specs}
    assert "predict_degradation" not in names          # planned → hidden from model
    assert "deep_research" in names
    with pytest.raises(Exception):
        spec_for("not_a_tool")
