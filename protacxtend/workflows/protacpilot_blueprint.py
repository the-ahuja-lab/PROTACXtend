"""PROTACpilot structural workflow blueprint (single source of truth).

Ordered node graph supplied by the PROTACpilot research design:

  PROTACpilot
   → Research Planner
   → KNOW target / KNOW E3 / KNOW PROTAC
   → Reference Structure Finder
   → PROTAC Decomposer
   → Binary Validator + Conformer Generator
   → Ternary Generator (COMPASS / PRosettaC / PROTAC-Model)
   → Pose Consensus
   → Interface scorer · Linker strain scorer · Cooperativity proxy
   → Full CRL Reconstruction → Lysine Proximity Scorer → MD Validator
   → bRo5 Exposure Predictor → Evidence Fusion Engine
   → Rank + Mechanistic Explanation → Reproducibility Report

Each node declares which PROTACXtend capability implements it today and its
honest availability: `engine` = real local step, `external` = requires a
configured external engine (never fabricated), `planned` = not implemented.
"""

from __future__ import annotations

from typing import Any, Dict, List

PROTACpILOT_BLUEPRINT: List[Dict[str, Any]] = [
    {"stage": "plan", "node": "research_planner",
     "desc": "Parse objective into target / E3 / PROTAC context.",
     "kind": "planner", "engine": "planner", "evidence": "USER INPUT"},
    {"stage": "KNOW", "node": "know_target",
     "desc": "Resolve target (UniProt/ChEMBL evidence).", "kind": "node",
     "engine": "resolve_target", "evidence": "RETRIEVED"},
    {"stage": "KNOW", "node": "know_e3",
     "desc": "E3 ligase evidence (local E3 catalog).", "kind": "node",
     "engine": "retrieve_e3_evidence", "evidence": "RETRIEVED"},
    {"stage": "KNOW", "node": "know_protac",
     "desc": "PROTAC / warhead SMILES input + inspection.", "kind": "node",
     "engine": "inspect_smiles", "evidence": "CALCULATED"},
    {"stage": "structure", "node": "reference_structure_finder",
     "desc": "Locate reference structures (PDB/AlphaFold ids).", "kind": "node",
     "engine": "retrieve_alphafold", "evidence": "RETRIEVED"},
    {"stage": "chemistry", "node": "protac_decomposer",
     "desc": "Decompose PROTAC into warhead · linker · E3 ligand.", "kind": "node",
     "engine": "decompose_brics", "evidence": "CALCULATED"},
    {"stage": "chemistry", "node": "binary_validator",
     "desc": "Validate each decomposed component SMILES.", "kind": "node",
     "engine": "inspect_smiles_multi", "evidence": "CALCULATED"},
    {"stage": "chemistry", "node": "conformer_generator",
     "desc": "Generate 3D conformers (RDKit).", "kind": "node",
     "engine": "conformer_3d", "evidence": "CALCULATED"},
    {"stage": "ternary", "node": "ternary_generator",
     "desc": "Ternary complex generation — PROTAC-Model (real backend; native outputs preserved).",
     "kind": "node", "engine": "protac_model",
     "external": ["COMPASS", "PRosettaC", "PROTAC-Model"], "evidence": "STRUCTURAL SURROGATE"},
    {"stage": "ternary", "node": "pose_consensus",
     "desc": "Consensus over ternary poses.", "kind": "node", "engine": None,
     "external": ["pose_consensus"], "evidence": "STRUCTURAL SURROGATE"},
    {"stage": "ternary", "node": "interface_scorer",
     "desc": "Target–E3 interface scoring.", "kind": "node", "engine": None,
     "external": ["interface_scorer"], "evidence": "STRUCTURAL SURROGATE"},
    {"stage": "ternary", "node": "linker_strain_scorer",
     "desc": "Linker strain scoring.", "kind": "node", "engine": None,
     "external": ["linker_strain"], "evidence": "STRUCTURAL SURROGATE"},
    {"stage": "ternary", "node": "cooperativity_proxy",
     "desc": "Cooperativity feasibility proxy.", "kind": "node",
     "engine": "predict_cooperativity", "evidence": "STRUCTURAL SURROGATE"},
    {"stage": "ternary", "node": "crl_reconstruction",
     "desc": "Full CRL (CRBN–Rbx1–Cul4) reconstruction.", "kind": "node",
     "engine": None, "external": ["crl_reconstruction"], "evidence": "STRUCTURAL SURROGATE"},
    {"stage": "ternary", "node": "lysine_proximity_scorer",
     "desc": "Lysine ubiquitination proximity scoring.", "kind": "node",
     "engine": "lysine_ubiquitination", "evidence": "STRUCTURAL SURROGATE"},
    {"stage": "dynamics", "node": "md_validator",
     "desc": "MD-based pose validation.", "kind": "node", "engine": None,
     "external": ["md_validator"], "evidence": "STRUCTURAL SURROGATE"},
    {"stage": "prediction", "node": "bRo5_exposure_predictor",
     "desc": "bRo5 exposure prediction.", "kind": "node", "engine": None,
     "external": ["bRo5"], "evidence": "ML PREDICTION"},
    {"stage": "decision", "node": "evidence_fusion_engine",
     "desc": "Fuse evidence with provenance + weights.", "kind": "node",
     "engine": "planner", "evidence": "CALCULATED"},
    {"stage": "decision", "node": "rank_explanation",
     "desc": "Rank + mechanistic explanation.", "kind": "node",
     "engine": "planner", "evidence": "CALCULATED"},
    {"stage": "report", "node": "reproducibility_report",
     "desc": "Reproducibility report artifact.", "kind": "node",
     "engine": "planner", "evidence": "CALCULATED"},
]

STAGE_ORDER = ["plan", "KNOW", "structure", "chemistry", "ternary", "dynamics",
               "prediction", "decision", "report"]


def blueprint_nodes() -> List[Dict[str, Any]]:
    return PROTACpILOT_BLUEPRINT


def node_names() -> List[str]:
    return [n["node"] for n in PROTACpILOT_BLUEPRINT]
