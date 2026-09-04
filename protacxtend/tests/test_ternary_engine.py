"""Modern ternary pose engine tests (structure, features, statuses, honesty)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "data/protac_repos/repos/PROTAC-Model_benchmark/structures"


def _inp(entry: str, poi: str, e3: str):
    from protacxtend.structural.engine import TernaryInput
    d = BENCH / entry
    return TernaryInput(poi_structure=str(d / "target.pdb"), e3_structure=str(d / "receptor.pdb"),
                        protac_smiles=(d / "protac.smi").read_text().strip(),
                        crystal_structure=str(d / f"{entry.lower()}_AD.pdb"),
                        poi_chain=poi, e3_chain=e3)


def test_parse_real_crystal_5t35():
    from protacxtend.structural import prep
    d = BENCH / "5T35"
    crystal = prep.read_pdb(d / "5t35_AD.pdb")
    assert "A" in crystal.chains and "D" in crystal.chains
    assert len(crystal.atoms) > 0


def test_parse_receptor_target_pairs():
    from protacxtend.structural import prep
    for entry in ("5T35", "6BN7"):
        d = BENCH / entry
        target = prep.read_pdb(d / "target.pdb")
        receptor = prep.read_pdb(d / "receptor.pdb")
        assert len(target.atoms) > 0 and len(receptor.atoms) > 0
        assert (d / "protac.smi").exists()


def test_pose_features_shape():
    from protacxtend.structural import prep
    from protacxtend.structural.engine import pose_features
    d = BENCH / "5T35"
    c = prep.read_pdb(d / "5t35_AD.pdb")
    lig = [a for a in c.heavy_atoms() if a.is_het and a.resname not in ("HOH", "H2O")]
    f = pose_features(c.chain_atoms("A"), c.chain_atoms("D"), lig)
    for k in ("protein_protein_clashes", "interface_contacts_4p5A",
              "hbond_proxy_N_O_3p6A", "anchor_min_distance_A"):
        assert isinstance(f[k], (int, float))


def test_crystal_reference_ensemble_output():
    from protacxtend.structural.engine import generate_ternary_ensemble
    out = generate_ternary_ensemble(_inp("5T35", "A", "D"), backend="crystal_reference", n_poses=8)
    assert out["status"] == "ok"
    assert out["n_generated"] == 8
    assert isinstance(out["native_rank"], int)
    for key in ("pose_id", "scores", "features"):
        assert key in out["poses"][0]


def test_modern_open_reports_not_available_without_backend(monkeypatch):
    from protacxtend.structural.engine import ModernOpenBackend, generate_ternary_ensemble
    monkeypatch.delenv("PROTACXTEND_DOCKER_ENGINE", raising=False)
    assert not ModernOpenBackend().available()["available"]
    out = generate_ternary_ensemble(_inp("5T35", "A", "D"), backend="modern_open")
    assert out["status"] == "NOT_AVAILABLE"
    assert "poses" not in out or out["poses"] == []


def test_legacy_backend_reports_unavailable_cleanly():
    from protacxtend.structural.engine import LegacyProtacModelBackend, generate_ternary_ensemble
    if LegacyProtacModelBackend().available()["available"]:
        pytest.skip("legacy deps unexpectedly present")
    out = generate_ternary_ensemble(_inp("5T35", "A", "D"), backend="legacy_protac_model")
    assert out["status"] == "NOT_AVAILABLE"
    assert "poses" not in out or out["poses"] == []
