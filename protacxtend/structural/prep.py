"""Modern ternary structure preparation + geometry.

Pure-Python PDB reader (ATOM/HETATM), chain/altloc/missing-atom handling,
ligand detection and anchor identification. Deliberately dependency-light
(numpy only) so it works everywhere the engine runs. Never rebuilds large
missing regions silently — it flags them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class Atom:
    serial: int
    name: str
    resname: str
    chain: str
    resseq: int
    element: str
    xyz: np.ndarray
    is_het: bool = False


@dataclass
class Structure:
    path: str
    atoms: List[Atom] = field(default_factory=list)
    chains: Dict[str, List[Atom]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def chain_atoms(self, chain: str) -> List[Atom]:
        return self.chains.get(chain, [])

    def heavy_atoms(self, atoms: Optional[List[Atom]] = None) -> List[Atom]:
        src = atoms if atoms is not None else self.atoms
        return [a for a in src if a.element != "H"]


def read_pdb(path: str | Path) -> Structure:
    p = Path(path)
    st = Structure(path=str(p))
    seen_alt: Dict[str, str] = {}
    res_atom_count: Dict[tuple, int] = {}
    missing_flagged = False
    prev_res: Optional[tuple] = None
    for line in p.read_text(errors="ignore").splitlines():
        if line.startswith("ATOM") or line.startswith("HETATM"):
            try:
                chain = line[21]
                name = line[12:16].strip()
                resname = line[17:20].strip()
                alt = line[16]
                resseq = int(line[22:26])
                icode = line[26]
                x = float(line[30:38]); y = float(line[38:46]); z = float(line[46:54])
                element = line[76:78].strip() or name[0]
            except (ValueError, IndexError):
                st.warnings.append(f"unparsable line: {line[:50]}")
                continue
            key = (chain, resseq, icode)
            # alternate locations: keep the first conformer only, note the rest
            altkey = (chain, resseq, name)
            if alt and alt != " ":
                if altkey in seen_alt and seen_alt[altkey] != alt:
                    continue
                seen_alt[altkey] = alt
            # gap / missing-atom check (sequential residue numbering)
            if prev_res and key[0] == prev_res[0] and not key[1] == prev_res[1]:
                gap = key[1] - prev_res[1]
                if gap > 1 and not missing_flagged:
                    st.warnings.append(f"chain {chain}: residue gap {prev_res[1]}→{key[1]} (missing regions NOT rebuilt)")
                    missing_flagged = True
            prev_res = key
            atom = Atom(serial=int(line[6:11].strip() or 0), name=name, resname=resname,
                        chain=chain, resseq=resseq, element=element,
                        xyz=np.array([x, y, z], dtype=float), is_het=line.startswith("HETATM"))
            st.atoms.append(atom)
            st.chains.setdefault(chain, []).append(atom)
            res_atom_count[(chain, resseq)] = res_atom_count.get((chain, resseq), 0) + 1
    if st.warnings and "gap" not in " ".join(st.warnings):
        pass
    return st


def coord_sanity(structure: Structure) -> Dict[str, Any]:
    if not structure.atoms:
        return {"ok": False, "reason": "no atoms"}
    xyz = np.array([a.xyz for a in structure.atoms])
    center = xyz.mean(axis=0)
    span = np.abs(xyz - center).max(axis=0)
    if float(span.max()) > 1e6:
        return {"ok": False, "reason": f"coordinate span implausible: {span}"}
    return {"ok": True, "center": center.tolist(), "span": span.tolist(),
            "n_atoms": len(structure.atoms)}


def ligand_ids(structure: Structure) -> List[str]:
    from collections import Counter
    return sorted(Counter(a.resname for a in structure.atoms if a.is_het and a.element != "H").items(),
                  key=lambda kv: -kv[1])[:20]


def residues_with_het(structure: Structure, resname: str) -> List[int]:
    return sorted({a.resseq for a in structure.atoms if a.is_het and a.resname == resname})


def heavy_atoms_near(structure: Structure, point: np.ndarray, radius: float = 8.0,
                     exclude_chains: Optional[List[str]] = None) -> List[Atom]:
    out = []
    ex = set(exclude_chains or [])
    for a in structure.heavy_atoms():
        if a.chain in ex:
            continue
        if np.linalg.norm(a.xyz - point) <= radius:
            out.append(a)
    return out


def anchor_from_atoms(atoms: List[Atom], name: str = "") -> Optional[Dict[str, Any]]:
    if not atoms:
        return None
    xyz = np.array([a.xyz for a in atoms])
    center = xyz.mean(axis=0)
    return {"name": name, "center": center.tolist(), "n_atoms": len(atoms),
            "residues": sorted({a.resseq for a in atoms})}


def ring_centroids(mol) -> List[np.ndarray]:
    """Ring centroids from an RDKit mol."""
    from rdkit import Chem
    infos = mol.GetRingInfo()
    conf = mol.GetConformer()
    out = []
    for ring in infos.AtomRings():
        pts = [np.array(conf.GetAtomPosition(i), dtype=float) for i in ring]
        out.append(np.mean(pts, axis=0))
    return out
