"""Modern ternary-complex pose engine.

Abstraction + backends:

  crystal_reference  — feature-validation mode; intentionally uses the
                       experimental ternary orientation (never for blind tests).
  modern_open        — production backend: restrained docking via a maintained
                       CLI (HADDOCK3 preferred, LightDock secondary). Reports
                       NOT_AVAILABLE when the backend is not installed — never
                       fabricates poses.
  legacy_protac_model— optional; reports UNAVAILABLE unless every legacy
                       dependency/license is valid (never auto-installs).

Output schema follows generate_ternary_ensemble() (engine section 16).
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from protacxtend.structural import prep
from protacxtend.workflows.pilot_runner import protac_model_status  # legacy gate


# ── anchors / reference inputs ───────────────────────────────────────────

@dataclass
class TernaryInput:
    poi_structure: str
    e3_structure: str
    protac_smiles: str
    crystal_structure: Optional[str] = None   # reference only
    poi_chain: str = "A"
    e3_chain: str = "D"
    poi_anchor: Optional[Dict[str, Any]] = None   # {chain, resseq, resname}
    e3_anchor: Optional[Dict[str, Any]] = None


# ── structure features (transparent, geometry-based) ─────────────────────

def _pairwise_min(xyz1: np.ndarray, xyz2: np.ndarray) -> float:
    if len(xyz1) == 0 or len(xyz2) == 0:
        return float("inf")
    # coarse blockwise minimum to keep memory sane
    best = float("inf")
    step = 256
    for i in range(0, len(xyz1), step):
        a = xyz1[i:i + step]
        for j in range(0, len(xyz2), step):
            b = xyz2[j:j + step]
            d = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
            m = float(d.min())
            if m < best:
                best = m
    return best


def pose_features(poi_atoms: List[prep.Atom], e3_atoms: List[prep.Atom],
                  protac_heavy: List[prep.Atom]) -> Dict[str, Any]:
    poi_xyz = np.array([a.xyz for a in poi_atoms]); e3_xyz = np.array([a.xyz for a in e3_atoms])
    lig_xyz = np.array([a.xyz for a in protac_heavy]) if protac_heavy else np.empty((0, 3))
    poi, e3, lig = poi_atoms, e3_atoms, protac_heavy

    def contacts(x, y, cutoff):
        count = 0
        step = 256
        for i in range(0, len(x), step):
            a = x[i:i + step]
            for j in range(0, len(y), step):
                b = y[j:j + step]
                d = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
                count += int((d < cutoff).sum())
        return count

    clash_pp = contacts(poi_xyz, e3_xyz, 2.0)
    clash_px = contacts(poi_xyz, lig_xyz, 2.0) + contacts(e3_xyz, lig_xyz, 2.0)
    iface_contacts = contacts(poi_xyz, e3_xyz, 4.5)
    iface_heavy_8 = contacts(poi_xyz, e3_xyz, 8.0)

    # H-bond / salt-bridge proxies by atom element + name heuristics
    def donor_accept_pairs(x, y):
        d_a = []
        for atoms, role in ((x, "d"), (y, "a")):
            for a in atoms:
                el = a.element.upper()
                nm = a.name.upper()
                if role == "d" and el == "N" and not (nm.startswith("N") and nm[1:].isdigit() is False):
                    d_a.append(a.xyz)
        return d_a
    # simpler: count N–O pairs < 3.6 Å
    donor = [a for a in poi if a.element.upper() == "N"]
    acc = [a for a in e3 if a.element.upper() == "O"]
    d2 = np.array([a.xyz for a in donor]) if donor else np.empty((0, 3))
    a2 = np.array([a.xyz for a in acc]) if acc else np.empty((0, 3))
    hbond_proxy = contacts(d2, a2, 3.6) if len(d2) and len(a2) else 0
    # hydrophobic contacts C–C < 4.5
    c_poi = [a for a in poi if a.element.upper() == "C"]
    c_e3 = [a for a in e3 if a.element.upper() == "C"]
    c1 = np.array([a.xyz for a in c_poi]) if c_poi else np.empty((0, 3))
    c2 = np.array([a.xyz for a in c_e3]) if c_e3 else np.empty((0, 3))
    hydrophobic = contacts(c1, c2, 4.5) if len(c1) and len(c2) else 0

    return {
        "protein_protein_clashes": clash_pp,
        "protac_protein_clashes": clash_px,
        "interface_contacts_4p5A": iface_contacts,
        "interface_atoms_within_8A": iface_heavy_8,
        "hbond_proxy_N_O_3p6A": hbond_proxy,
        "hydrophobic_C_C_4p5A": hydrophobic,
        "anchor_min_distance_A": round(float(_pairwise_min(poi_xyz, e3_xyz)), 2),
    }


# ── decoy ensemble (crystal_reference mode) ──────────────────────────────

def _rot(axis: np.ndarray, angle: float) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    a = angle
    c, s = math.cos(a), math.sin(a)
    C = 1 - c
    x, y, z = axis
    return np.array([
        [x * x * C + c, x * y * C - z * s, x * z * C + y * s],
        [y * x * C + z * s, y * y * C + c, y * z * C - x * s],
        [z * x * C - y * s, z * y * C + x * s, z * z * C + c],
    ])


def translate_atoms(atoms: List[prep.Atom], R: np.ndarray, t: np.ndarray,
                    center: np.ndarray) -> List[prep.Atom]:
    out = []
    for a in atoms:
        moved = R @ (a.xyz - center) + center + t
        out.append(prep.Atom(a.serial, a.name, a.resname, a.chain, a.resseq,
                             a.element, moved, a.is_het))
    return out


# ── consensus scoring (components; weights heuristic/untrained) ─────────

WEIGHTS = {"w1_dock": 1.0, "w2_linker": 1.0, "w3_interface": 1.0,
           "w4_anchor": 1.0, "w5_clash": 1.0}


def score_ternary_pose(features: Dict[str, Any], linker: Dict[str, Any],
                       native_scale: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    ns = native_scale or {}
    def z(key, fallback_min, fallback_max, invert=True):
        lo = ns.get(key + "_min", fallback_min); hi = ns.get(key + "_max", fallback_max)
        v = features.get(key, 0)
        span = max(hi - lo, 1e-6)
        norm = (v - lo) / span
        return (1 - norm) if invert else norm

    S_clash = z("protein_protein_clashes", 0, 200) + z("protac_protein_clashes", 0, 400)
    S_interface = z("interface_contacts_4p5A", 0, 400, invert=False) + \
        z("hbond_proxy_N_O_3p6A", 0, 60, invert=False) * 0.5
    S_anchor = z("anchor_min_distance_A", 3, 60)
    S_linker = 0.0
    if linker:
        S_linker = 0.0 if linker.get("linker_reachable") else 1.0
    S_docking = (1.0 - S_clash) * 0.5 + S_interface * 0.5  # heuristic surrogate
    S_pose = (WEIGHTS["w1_dock"] * S_docking + WEIGHTS["w2_linker"] * (1 - S_linker) +
              WEIGHTS["w3_interface"] * S_interface + WEIGHTS["w4_anchor"] * (1 - S_anchor)
              - WEIGHTS["w5_clash"] * S_clash)
    return {"S_docking": round(S_docking, 4), "S_linker": round(1 - S_linker, 4),
            "S_clash": round(S_clash, 4), "S_interface": round(S_interface, 4),
            "S_anchor": round(1 - S_anchor, 4), "consensus_score": round(S_pose, 4)}


def cluster_poses(pose_signatures: List[Dict[str, Any]], rmsd_cutoff: float = 6.0) -> Dict[str, Any]:
    """Simple greedy clustering on interface heavy-atom coordinates."""
    centers = []
    members: List[List[int]] = []
    for idx, sig in enumerate(pose_signatures):
        coords = sig.get("interface_coords")
        if coords is None:
            continue
        placed = False
        for ci, c in enumerate(centers):
            if rmsd(coords, c) <= rmsd_cutoff:
                members[ci].append(idx); placed = True; break
        if not placed:
            centers.append(coords); members.append([idx])
    if not centers:
        return {"n_clusters": 0, "dominant_cluster_fraction": 0.0,
                "cluster_members": []}
    sizes = [len(m) for m in members]
    dom = max(sizes) / max(sum(sizes), 1)
    return {"n_clusters": len(members), "dominant_cluster_fraction": round(dom, 3),
            "cluster_members": [sorted(m) for m in members]}


def rmsd(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a); b = np.asarray(b)
    n = min(len(a), len(b))
    if n == 0:
        return float("inf")
    return float(np.sqrt(np.mean(np.sum((a[:n] - b[:n]) ** 2, axis=1))))


# ── engine ───────────────────────────────────────────────────────────────

class TernaryPoseEngine:
    backend = "abstract"

    def available(self) -> Dict[str, Any]:
        return {"backend": self.backend, "available": False, "reason": "abstract"}

    def generate_poses(self, inp: TernaryInput, n_poses: int = 10,
                       progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        raise NotImplementedError


class CrystalReferenceBackend(TernaryPoseEngine):
    """Feature validation only — intentionally uses experimental geometry."""

    backend = "crystal_reference"

    def available(self) -> Dict[str, Any]:
        return {"backend": self.backend, "available": True,
                "reason": "reference/validation mode (not blind docking)"}

    def generate_poses(self, inp: TernaryInput, n_poses: int = 10,
                       progress=None, decoys_per_axis: int = 6) -> Dict[str, Any]:
        t0 = time.time()
        crystal = prep.read_pdb(inp.crystal_structure)
        target_atoms = crystal.chain_atoms(inp.poi_chain)
        e3_atoms = crystal.chain_atoms(inp.e3_chain)
        if not target_atoms or not e3_atoms:
            return {"backend": self.backend, "status": "NOT_AVAILABLE",
                    "reason": "crystal chains missing"}
        # protac heavy atoms = HETATM residues except ions/waters
        lig_heavy = [a for a in crystal.heavy_atoms() if a.is_het and a.resname not in ("HOH", "H2O")]
        feat = pose_features(target_atoms, e3_atoms, lig_heavy)

        # decoys: rotate the E3 body around its own centre on random axes
        xyz_e3 = np.array([a.xyz for a in e3_atoms])
        centre = xyz_e3.mean(axis=0)
        rng = np.random.default_rng(20260903)
        poses = []
        native_sig = np.array([a.xyz for a in e3_atoms if a.element != "H"])
        sig_all = []
        for i in range(n_poses):
            is_native = i == 0
            if is_native:
                moved = e3_atoms
                r, t = np.eye(3), np.zeros(3)
            else:
                axis = rng.normal(size=3)
                ang = rng.uniform(0.06, 0.35)
                r = _rot(axis, ang)
                t = rng.normal(scale=1.6, size=3)
                moved = translate_atoms(e3_atoms, r, t, centre)
            feats = pose_features(target_atoms, moved, lig_heavy)
            score = score_ternary_pose(feats, {})
            poses.append({"pose_id": f"pose_{i:02d}", "native": is_native,
                          "rotation_deg": 0.0 if is_native else round(math.degrees(ang), 1),
                          "features": feats, "scores": score})
            if i == 0:
                sig_all.append(sig_all)  # placeholder no-op
            sig_all.append(np.array([a.xyz for a in moved if a.element != "H"]))

        clustering = cluster_poses(
            [{"interface_coords": c} for c in sig_all if isinstance(c, np.ndarray)])
        ranked = sorted(poses, key=lambda p: -p["scores"]["consensus_score"])
        native_rank = next((i for i, p in enumerate(ranked) if p["native"]), None)
        return {
            "backend": self.backend, "status": "ok",
            "backend_version": "0.1-crystal-reference",
            "n_generated": len(poses), "n_ranked": len(poses),
            "poses": poses, "ranking": ranked,
            "native_rank": native_rank,
            "native_top1": native_rank == 0, "native_top5": native_rank is not None and native_rank < 5,
            "ensemble": {"clusters": clustering.get("n_clusters"),
                         "dominant_cluster_fraction": clustering.get("dominant_cluster_fraction")},
            "runtime_s": round(time.time() - t0, 2),
        }


class ModernOpenBackend(TernaryPoseEngine):
    """Production backend — restrained docking via a maintained CLI.

    Available when HADDOCK3 (preferred) or LightDock is installed and pointed
    to via PROTACXTEND_DOCKER_ENGINE env var. Everything else reports
    NOT_AVAILABLE honestly.
    """

    backend = "modern_open"

    def available(self) -> Dict[str, Any]:
        engine = os.environ.get("PROTACXTEND_DOCKER_ENGINE", "").strip()
        if engine and (Path(engine).exists() or subprocess.run(["which", engine],
                        capture_output=True).returncode == 0):
            return {"backend": self.backend, "available": True, "engine": engine}
        return {"backend": self.backend, "available": False,
                "reason": "no maintained docking backend configured "
                          "(see docs/TERNARY_BACKEND_AUDIT.md: HADDOCK3 primary, LightDock secondary)"}

    def generate_poses(self, inp: TernaryInput, n_poses: int = 10, progress=None):
        avail = self.available()
        if not avail["available"]:
            return {"backend": self.backend, "status": "NOT_AVAILABLE",
                    "reason": avail["reason"], "n_generated": 0, "poses": []}
        raise NotImplementedError("HADDOCK3/LightDock invocation adapter is the next build step")


class LegacyProtacModelBackend(TernaryPoseEngine):
    backend = "legacy_protac_model"

    def available(self) -> Dict[str, Any]:
        st = protac_model_status()
        return {"backend": self.backend, "available": st.get("ready", False),
                "reason": "" if st.get("ready") else
                "legacy dependencies/licence unavailable — see docs/LEGACY_PROTAC_MODEL.md"}

    def generate_poses(self, inp: TernaryInput, n_poses: int = 10, progress=None):
        from protacxtend.workflows.pilot_runner import run_protac_model
        if not self.available()["available"]:
            return {"backend": self.backend, "status": "NOT_AVAILABLE",
                    "reason": self.available()["reason"]}
        return run_protac_model({"target": inp.poi_chain, "e3": inp.e3_chain,
                                 "smoke_inputs": {"receptor": inp.e3_structure,
                                                  "target": inp.poi_structure,
                                                  "smiles": inp.protac_smiles}})


BACKENDS = {b.backend: b for b in (CrystalReferenceBackend(), ModernOpenBackend(),
                                   LegacyProtacModelBackend())}


def generate_ternary_ensemble(inp: TernaryInput, backend: str = "modern_open",
                              n_poses: int = 10,
                              progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """Agent-facing router. modern → crystal_reference fallback is NOT used
    automatically for blind docking (would invalidate results); the caller
    must explicitly request crystal_reference for feature validation."""
    if backend not in BACKENDS:
        return {"status": "NOT_AVAILABLE", "reason": f"unknown backend '{backend}'"}
    eng = BACKENDS[backend]
    if not eng.available()["available"] and backend != "crystal_reference":
        return {"status": "NOT_AVAILABLE", "reason": eng.available()["reason"],
                "backend": backend, "warnings": ["backend unavailable — no poses fabricated"]}
    return eng.generate_poses(inp, n_poses=n_poses, progress=progress)
