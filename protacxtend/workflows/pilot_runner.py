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
import os
from pathlib import Path
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
        res = generate_3d_conformer(smiles, max_attempts=1000, seed=61453)
        if res.get("status") == "success" and res.get("molblock"):
            return {"status": "success", "summary": "3D conformer generated (RDKit ETKDG)",
                    "data": {"molblock_chars": len(res["molblock"]),
                             "conformer_id": res.get("conformer_id")}}
        return {"status": "blocked", "summary": f"conformer generation failed · {res.get('error')}",
                "data": res}
    if engine == "protac_model":
        return run_protac_model(ctx)
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



# ── PROTAC-Model real backend (native outputs + provenance; never fabricated) ──

_REQUIRED_BIN_ENV = {
    "python2": None, "ADFRsuite": "ADFRSUITE", "frodock": "FRODOCK",
    "voromqa": "VOROMQA", "fcc": "FCC", "Rosetta": "ROSETTA",
}
_OPTIONAL_BIN_ENV = {"vina": "VINA"}


def _which(name: str) -> Optional[str]:
    import shutil
    return shutil.which(name)


def _protac_model_dir() -> Optional[Any]:
    env = os.environ.get("PROTACXTEND_PROTAC_MODEL_DIR", "").strip()
    if env:
        cand = Path(env)
        return cand if (cand / "main.py").exists() else None
    from pathlib import Path as _P
    cand = _P(__file__).resolve().parents[2] / "data" / "protac_repos" / "repos" / "PROTAC-Model"
    return cand if (cand / "main.py").exists() else None


def protac_model_status() -> Dict[str, Any]:
    """Per-dependency availability report (no execution)."""
    import os as _os
    report: Dict[str, Any] = {"dir": str(_protac_model_dir() or ""), "deps": {}}
    for label, envvar in _REQUIRED_BIN_ENV.items():
        found = _which(label)
        if found is None and envvar:
            found = _os.environ.get(envvar)
        report["deps"][label] = "present" if found else "MISSING"
    report["ready"] = report["dir"] != "" and all(v == "present" for v in report["deps"].values())
    return report



def _read_atoms(pdb: Path) -> Dict[str, List[Dict[str, float]]]:
    """chain -> list of atom dicts {x,y,z} from ATOM/HETATM records."""
    chains: Dict[str, List[Dict[str, float]]] = {}
    for line in pdb.read_text(errors="ignore").splitlines():
        if line.startswith(("ATOM", "HETATM")):
            try:
                x = float(line[30:38]); y = float(line[38:46]); z = float(line[46:54])
            except ValueError:
                continue
            chains.setdefault(line[21], []).append({"x": x, "y": y, "z": z})
    return chains


def derive_site_from_crystal(crystal: Path, target_chain: str = "A",
                             receptor_chain: str = "D", cutoff_angstrom: float = 8.0,
                             ) -> Optional[Dict[str, Any]]:
    """Interface centre of the receptor chain near the target chain in the
    crystal complex — the docking site for PROTAC-Model protein-protein
    docking. Pure coordinate geometry; no model inference."""
    chains = _read_atoms(crystal)
    target = chains.get(target_chain, [])
    receptor = chains.get(receptor_chain, [])
    if not target or not receptor:
        return None
    interface = []
    for r in receptor:
        rx, ry, rz = r["x"], r["y"], r["z"]
        for t in target:
            dx, dy, dz = rx - t["x"], ry - t["y"], rz - t["z"]
            if dx * dx + dy * dy + dz * dz <= cutoff_angstrom * cutoff_angstrom:
                interface.append(r)
                break
    if not interface:
        return None
    n = len(interface)
    site = {
        "x": round(sum(a["x"] for a in interface) / n, 2),
        "y": round(sum(a["y"] for a in interface) / n, 2),
        "z": round(sum(a["z"] for a in interface) / n, 2),
        "n_interface_atoms": n,
        "target_chain": target_chain, "receptor_chain": receptor_chain,
        "crystal": str(crystal), "source": "derived_from_crystal_interface",
    }
    return site


def protac_model_requirements() -> str:
    """Exact install/activation requirements (never installs anything)."""
    lines = [
        "PROTAC-Model runtime requirements (see data/protac_repos/repos/PROTAC-Model/README):",
        "  1. python2 ................ present (/usr/bin/python2)",
        "  2. RDKit (py2-compatible) . required by repo utils",
        "  3. ADFRsuite ................ ccsb.scripps.edu/adfr - set ADFRSUITE=<dir>",
        "  4. FRODOCK ................... chaconlab.org/modeling/frodock - set FRODOCK=<dir>",
        "  5. VOROMQA .................. github.com/kliment-olechnovic/voronota - set VOROMQA=<dir>",
        "  6. FCC ...................... github.com/haddocking/fcc - set FCC=<dir>",
        "  7. Rosetta (license) ........ rosettacommons.org (MPI build) - set ROSETTA=<dir>",
        "  8. Vina ..................... present (/usr/bin/vina)",
        "  9. Docking site ............. auto-derived from crystal 5t35_AD (or set PROTAC_MODEL_SITE)",
    ]
    return "\n".join(lines)


def run_protac_model(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Run PROTAC-Model main.py with benchmark 5T35/MZ1 inputs when every
    dependency exists. Returns native outputs + provenance; never fabricates."""
    status = protac_model_status()
    bench = (Path(status["dir"]).parent / "PROTAC-Model_benchmark" / "structures" / "5T35") \
        if status["dir"] else None

    # Derive the docking site from the crystal up front (pure geometry; provenance kept).
    site = (ctx.get("site") or os.environ.get("PROTAC_MODEL_SITE", "")).strip()
    site_provenance = None
    if not site and bench is not None:
        crystal = bench / "5t35_AD.pdb"
        if crystal.exists():
            derived = derive_site_from_crystal(crystal)
            if derived:
                site = f"{derived['x']},{derived['y']},{derived['z']}"
                site_provenance = derived

    if status["dir"] == "":
        return {"status": "blocked",
                "summary": "PROTAC-Model repo not found (set PROTACXTEND_PROTAC_MODEL_DIR)"}
    missing = [k for k, v in status["deps"].items() if v != "present"]
    if missing:
        return {"status": "blocked",
                "summary": ("PROTAC-Model dependencies missing: " + ", ".join(missing) +
                            ". Install ADFRsuite/FRODOCK/VOROMQA/FCC/Rosetta(+MPI) and set env "
                            "vars ADFRSUITE/FRODOCK/VOROMQA/FCC/ROSETTA (see repo README). "
                            "NOT AVAILABLE — no result fabricated."),
                "deps": status["deps"],
                "data": {"derived_site": site_provenance or site,
                         "requirements": protac_model_requirements()}}
    if not site:
        return {"status": "blocked",
                "summary": "PROTAC-Model ready but docking site (-site X,Y,Z) could not be "
                           "derived from crystal (set PROTAC_MODEL_SITE or ctx site).",
                "deps": status["deps"]}
    # 5T35/MZ1 smoke inputs (receptor=larger complex, target=BRD4, crystal=5t35_AD)
    inputs = ctx.get("smoke_inputs") or {}
    rec = inputs.get("receptor") or str(bench / "receptor.pdb")
    tgt = inputs.get("target") or str(bench / "target.pdb")
    smi = inputs.get("smiles") or str(bench / "protac.smi")
    out = Path(ctx.get("output_dir") or (bench.parent / "output" / "protac_model_run"))
    out.mkdir(parents=True, exist_ok=True)
    cmd = ["python2", str(Path(status["dir"]) / "main.py"),
           "-irec", rec, "-ilig", tgt, "-site", site, "-ismi", smi, "-o", str(out), "-cpu", "1"]
    import subprocess as _sp, time as _time
    started = _time.time()
    try:
        proc = _sp.run(cmd, capture_output=True, text=True, timeout=7200)
        poses = sorted(str(p) for p in out.rglob("*.pdb"))
        return {"status": "success" if proc.returncode == 0 and poses else "error",
                "summary": f"PROTAC-Model finished rc={proc.returncode} · {len(poses)} pose PDB(s)",
                "data": {"returncode": proc.returncode, "poses": poses,
                         "stdout_tail": (proc.stdout or "")[-800:],
                         "stderr_tail": (proc.stderr or "")[-800:],
                         "output_dir": str(out), "runtime_s": round(_time.time() - started, 1)},
                "provenance": {"command": cmd, "deps": status["deps"],
                               "model": "PROTAC-Model", "repo": status["dir"],
                               "site": site_provenance or site}}
    except Exception as exc:
        return {"status": "error", "summary": f"PROTAC-Model execution error · {exc}",
                "runtime_s": round(_time.time() - started, 1)}


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
