"""RDKit-based chemistry core for PROTACXtend.

The functions in this module are deliberately small, structured, and safe for
workflow use: invalid user chemistry returns explicit failed status instead of
raising, and no external services or heavy docking/training tools are invoked.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any


try:  # pragma: no cover - availability is exercised in tests when installed.
    from rdkit import Chem, DataStructs
    from rdkit.Chem import AllChem, Crippen, Descriptors, Lipinski, QED, rdMolDescriptors
    from rdkit.Chem.rdchem import Mol

    RDKIT_AVAILABLE = True
    RDKIT_IMPORT_ERROR: str | None = None
except Exception as exc:  # pragma: no cover - depends on environment.
    Chem = None
    DataStructs = None
    AllChem = None
    Crippen = None
    Descriptors = None
    Lipinski = None
    QED = None
    rdMolDescriptors = None
    Mol = Any
    RDKIT_AVAILABLE = False
    RDKIT_IMPORT_ERROR = f"RDKit is not available: {exc}"


@dataclass
class ChemicalValidationResult:
    input_smiles: str
    valid: bool
    canonical_smiles: str | None
    isomeric_canonical_smiles: str | None
    error: str | None
    num_atoms: int | None
    num_heavy_atoms: int | None
    formal_charge: int | None
    fragments: int | None
    largest_fragment_smiles: str | None
    warnings: list[str] = field(default_factory=list)


@dataclass
class DescriptorResult:
    smiles: str
    canonical_smiles: str
    mw: float
    exact_mw: float
    tpsa: float
    logp: float
    hbd: int
    hba: int
    rotatable_bonds: int
    ring_count: int
    aromatic_ring_count: int
    heavy_atom_count: int
    fraction_csp3: float
    qed: float | None
    descriptor_backend: str
    descriptor_status: str


@dataclass
class FingerprintResult:
    smiles: str
    canonical_smiles: str
    fingerprint_type: str
    radius: int
    n_bits: int
    bit_count: int
    backend: str
    status: str


@dataclass
class SubstructureMatchResult:
    query_smarts: str
    target_smiles: str
    matched: bool
    num_matches: int
    atom_indices: list[list[int]]
    error: str | None


@dataclass
class ProtacComponentAnalysis:
    full_smiles: str
    canonical_smiles: str | None
    valid: bool
    mw: float | None
    tpsa: float | None
    logp: float | None
    hbd: int | None
    hba: int | None
    rotatable_bonds: int | None
    linker_like_warning: bool
    protac_size_warning: bool
    high_logp_warning: bool
    high_tpsa_warning: bool
    excessive_rotatable_bonds_warning: bool
    medicinal_chemistry_notes: list[str] = field(default_factory=list)


def _failed_validation(smiles: str, error: str) -> ChemicalValidationResult:
    return ChemicalValidationResult(
        input_smiles=smiles,
        valid=False,
        canonical_smiles=None,
        isomeric_canonical_smiles=None,
        error=error,
        num_atoms=None,
        num_heavy_atoms=None,
        formal_charge=None,
        fragments=None,
        largest_fragment_smiles=None,
        warnings=[],
    )


def _failed_descriptor(smiles: str, status: str) -> DescriptorResult:
    return DescriptorResult(
        smiles=smiles,
        canonical_smiles="",
        mw=0.0,
        exact_mw=0.0,
        tpsa=0.0,
        logp=0.0,
        hbd=0,
        hba=0,
        rotatable_bonds=0,
        ring_count=0,
        aromatic_ring_count=0,
        heavy_atom_count=0,
        fraction_csp3=0.0,
        qed=None,
        descriptor_backend="rdkit" if RDKIT_AVAILABLE else "none",
        descriptor_status=status,
    )


def safe_mol_from_smiles(smiles: str, sanitize: bool = True) -> tuple[Mol | None, str | None]:
    """Parse a SMILES string without throwing on bad user input."""

    if not RDKIT_AVAILABLE:
        return None, RDKIT_IMPORT_ERROR
    text = (smiles or "").strip()
    if not text:
        return None, "SMILES is required."
    try:
        mol = Chem.MolFromSmiles(text, sanitize=False)
        if mol is None:
            return None, "RDKit could not parse SMILES."
        if sanitize:
            Chem.SanitizeMol(mol)
        return mol, None
    except Exception as exc:
        return None, f"RDKit parse/sanitize failed: {exc}"


def largest_fragment_mol(mol: Mol) -> Mol:
    """Return the fragment with the largest heavy atom count."""

    if mol is None or not RDKIT_AVAILABLE:
        return mol
    fragments = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True)
    if not fragments:
        return mol
    return max(fragments, key=lambda item: (item.GetNumHeavyAtoms(), item.GetNumAtoms()))


def canonicalize_smiles(smiles: str, isomeric: bool = True, largest_fragment: bool = False) -> ChemicalValidationResult:
    mol, error = safe_mol_from_smiles(smiles, sanitize=True)
    if error or mol is None:
        return _failed_validation(smiles, error or "Unknown RDKit parsing error.")

    warnings: list[str] = []
    fragments = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True)
    fragment_count = len(fragments)
    largest = largest_fragment_mol(mol)
    largest_fragment_smiles = Chem.MolToSmiles(largest, canonical=True, isomericSmiles=isomeric) if largest is not None else None
    working = largest if largest_fragment else mol
    if fragment_count > 1:
        warnings.append("Molecule contains multiple fragments or salt components.")
        if largest_fragment:
            warnings.append("Canonical output uses the largest fragment only.")

    try:
        canonical = Chem.MolToSmiles(working, canonical=True, isomericSmiles=False)
        isomeric_canonical = Chem.MolToSmiles(working, canonical=True, isomericSmiles=True)
    except Exception as exc:
        return _failed_validation(smiles, f"RDKit canonicalization failed: {exc}")

    return ChemicalValidationResult(
        input_smiles=smiles,
        valid=True,
        canonical_smiles=isomeric_canonical if isomeric else canonical,
        isomeric_canonical_smiles=isomeric_canonical,
        error=None,
        num_atoms=int(working.GetNumAtoms()),
        num_heavy_atoms=int(working.GetNumHeavyAtoms()),
        formal_charge=int(sum(atom.GetFormalCharge() for atom in working.GetAtoms())),
        fragments=fragment_count,
        largest_fragment_smiles=largest_fragment_smiles,
        warnings=warnings,
    )


def validate_smiles(smiles: str) -> ChemicalValidationResult:
    return canonicalize_smiles(smiles)


def compute_descriptors(smiles: str) -> DescriptorResult:
    mol, error = safe_mol_from_smiles(smiles, sanitize=True)
    if error or mol is None:
        return _failed_descriptor(smiles, f"failed: {error or 'unknown error'}")
    try:
        canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        return DescriptorResult(
            smiles=smiles,
            canonical_smiles=canonical,
            mw=float(Descriptors.MolWt(mol)),
            exact_mw=float(Descriptors.ExactMolWt(mol)),
            tpsa=float(rdMolDescriptors.CalcTPSA(mol)),
            logp=float(Crippen.MolLogP(mol)),
            hbd=int(Lipinski.NumHDonors(mol)),
            hba=int(Lipinski.NumHAcceptors(mol)),
            rotatable_bonds=int(Lipinski.NumRotatableBonds(mol)),
            ring_count=int(rdMolDescriptors.CalcNumRings(mol)),
            aromatic_ring_count=int(rdMolDescriptors.CalcNumAromaticRings(mol)),
            heavy_atom_count=int(mol.GetNumHeavyAtoms()),
            fraction_csp3=float(rdMolDescriptors.CalcFractionCSP3(mol)),
            qed=float(QED.qed(mol)) if QED is not None else None,
            descriptor_backend="rdkit",
            descriptor_status="success",
        )
    except Exception as exc:
        return _failed_descriptor(smiles, f"failed: RDKit descriptor calculation failed: {exc}")


def morgan_fingerprint(smiles: str, radius: int = 2, n_bits: int = 2048) -> FingerprintResult:
    mol, error = safe_mol_from_smiles(smiles, sanitize=True)
    if error or mol is None:
        return FingerprintResult(smiles, "", "morgan", radius, n_bits, 0, "rdkit" if RDKIT_AVAILABLE else "none", f"failed: {error}")
    if radius < 0 or n_bits <= 0:
        return FingerprintResult(smiles, "", "morgan", radius, n_bits, 0, "rdkit", "failed: radius must be non-negative and n_bits must be positive.")
    try:
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius, nBits=n_bits)
        return FingerprintResult(
            smiles=smiles,
            canonical_smiles=Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True),
            fingerprint_type="morgan",
            radius=radius,
            n_bits=n_bits,
            bit_count=len(list(fp.GetOnBits())),
            backend="rdkit",
            status="success",
        )
    except Exception as exc:
        return FingerprintResult(smiles, "", "morgan", radius, n_bits, 0, "rdkit", f"failed: {exc}")


def _morgan_bitvect(smiles: str, radius: int, n_bits: int) -> tuple[Any | None, str | None, str | None]:
    mol, error = safe_mol_from_smiles(smiles, sanitize=True)
    if error or mol is None:
        return None, None, error
    try:
        canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius, nBits=n_bits)
        return fp, canonical, None
    except Exception as exc:
        return None, None, f"RDKit Morgan fingerprint failed: {exc}"


def tanimoto_similarity(smiles_a: str, smiles_b: str, radius: int = 2, n_bits: int = 2048) -> dict[str, Any]:
    fp_a, canonical_a, error_a = _morgan_bitvect(smiles_a, radius, n_bits)
    fp_b, canonical_b, error_b = _morgan_bitvect(smiles_b, radius, n_bits)
    if error_a or error_b or fp_a is None or fp_b is None:
        return {
            "smiles_a": smiles_a,
            "smiles_b": smiles_b,
            "canonical_a": canonical_a,
            "canonical_b": canonical_b,
            "similarity": None,
            "status": "failed",
            "error": error_a or error_b or "Fingerprint generation failed.",
        }
    try:
        similarity = float(DataStructs.TanimotoSimilarity(fp_a, fp_b))
    except Exception as exc:
        return {
            "smiles_a": smiles_a,
            "smiles_b": smiles_b,
            "canonical_a": canonical_a,
            "canonical_b": canonical_b,
            "similarity": None,
            "status": "failed",
            "error": f"RDKit Tanimoto calculation failed: {exc}",
        }
    return {
        "smiles_a": smiles_a,
        "smiles_b": smiles_b,
        "canonical_a": canonical_a,
        "canonical_b": canonical_b,
        "similarity": similarity,
        "status": "success",
        "error": None,
    }


def substructure_search(target_smiles: str, query_smarts: str) -> SubstructureMatchResult:
    mol, error = safe_mol_from_smiles(target_smiles, sanitize=True)
    if error or mol is None:
        return SubstructureMatchResult(query_smarts, target_smiles, False, 0, [], error)
    try:
        query = Chem.MolFromSmarts((query_smarts or "").strip())
    except Exception as exc:
        query = None
        error = f"RDKit SMARTS parsing failed: {exc}"
    if query is None:
        return SubstructureMatchResult(query_smarts, target_smiles, False, 0, [], error or "Invalid SMARTS query.")
    matches = [list(match) for match in mol.GetSubstructMatches(query)]
    return SubstructureMatchResult(query_smarts, target_smiles, bool(matches), len(matches), matches, None)


def detect_attachment_points(smiles: str) -> dict[str, Any]:
    text = smiles or ""
    mol, error = safe_mol_from_smiles(text, sanitize=False)
    atom_map_numbers: list[int] = []
    dummy_atom_indices: list[int] = []
    if mol is not None:
        for atom in mol.GetAtoms():
            if atom.GetAtomMapNum():
                atom_map_numbers.append(int(atom.GetAtomMapNum()))
            if atom.GetAtomicNum() == 0:
                dummy_atom_indices.append(int(atom.GetIdx()))
    else:
        atom_map_numbers = [int(value) for value in re.findall(r":(\d+)\]", text)]
        dummy_atom_indices = list(range(len(re.findall(r"\[\*:?\d*\]|\[R\]", text))))

    num_dummy_atoms = len(dummy_atom_indices)
    has_valid_two_point_attachment = num_dummy_atoms >= 2 and len(set(atom_map_numbers)) >= 2
    warning = None
    status = "success"
    if error and not dummy_atom_indices:
        status = "failed"
        warning = error
    elif num_dummy_atoms == 0:
        status = "no_attachment_points"
        warning = "No dummy attachment atoms were detected."
    elif num_dummy_atoms == 1:
        warning = "Only one dummy attachment atom was detected."
    elif not has_valid_two_point_attachment:
        warning = "Two or more dummy atoms detected, but distinct atom-map numbers are missing."

    return {
        "num_dummy_atoms": num_dummy_atoms,
        "atom_map_numbers": sorted(set(atom_map_numbers)),
        "dummy_atom_indices": dummy_atom_indices,
        "has_valid_two_point_attachment": has_valid_two_point_attachment,
        "status": status,
        "warning": warning,
    }


def strip_dummy_atoms_to_hydrogen(smiles: str) -> dict[str, Any]:
    mol, error = safe_mol_from_smiles(smiles, sanitize=False)
    if error or mol is None:
        return {"input_smiles": smiles, "product_smiles": None, "status": "failed", "error": error}
    try:
        rw_mol = Chem.RWMol(mol)
        dummy_indices = [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetAtomicNum() == 0]
        for idx in sorted(dummy_indices, reverse=True):
            rw_mol.RemoveAtom(idx)
        product = rw_mol.GetMol()
        Chem.SanitizeMol(product)
        return {
            "input_smiles": smiles,
            "product_smiles": Chem.MolToSmiles(product, canonical=True, isomericSmiles=True),
            "status": "success",
            "error": None,
        }
    except Exception as exc:
        return {"input_smiles": smiles, "product_smiles": None, "status": "failed", "error": f"Dummy atom stripping failed: {exc}"}


def generate_2d_molblock(smiles: str) -> dict[str, Any]:
    mol, error = safe_mol_from_smiles(smiles, sanitize=True)
    if error or mol is None:
        return {"smiles": smiles, "status": "failed", "molblock": None, "error": error}
    try:
        AllChem.Compute2DCoords(mol)
        return {"smiles": smiles, "status": "success", "molblock": Chem.MolToMolBlock(mol), "error": None}
    except Exception as exc:
        return {"smiles": smiles, "status": "failed", "molblock": None, "error": f"2D coordinate generation failed: {exc}"}


def generate_3d_conformer(smiles: str, max_attempts: int = 1000, seed: int = 61453) -> dict[str, Any]:
    mol, error = safe_mol_from_smiles(smiles, sanitize=True)
    if error or mol is None:
        return {"smiles": smiles, "status": "failed", "conformer_id": None, "molblock": None, "error": error}
    try:
        mol_h = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = int(seed)
        if hasattr(params, "maxAttempts"):
            params.maxAttempts = int(max_attempts)
        elif hasattr(params, "maxIterations"):   # RDKit >= 2024 removed maxAttempts
            params.maxIterations = int(max(50, max_attempts))
        conformer_id = int(AllChem.EmbedMolecule(mol_h, params))
        if conformer_id < 0:
            return {"smiles": smiles, "status": "failed", "conformer_id": conformer_id, "molblock": None, "error": "RDKit ETKDG embedding failed."}
        try:
            AllChem.UFFOptimizeMolecule(mol_h, confId=conformer_id, maxIters=200)
        except Exception:
            pass
        return {"smiles": smiles, "status": "success", "conformer_id": conformer_id, "molblock": Chem.MolToMolBlock(mol_h, confId=conformer_id), "error": None}
    except Exception as exc:
        return {"smiles": smiles, "status": "failed", "conformer_id": None, "molblock": None, "error": f"3D conformer generation failed: {exc}"}


def analyze_protac_like_properties(smiles: str) -> ProtacComponentAnalysis:
    validation = validate_smiles(smiles)
    if not validation.valid:
        return ProtacComponentAnalysis(
            full_smiles=smiles,
            canonical_smiles=None,
            valid=False,
            mw=None,
            tpsa=None,
            logp=None,
            hbd=None,
            hba=None,
            rotatable_bonds=None,
            linker_like_warning=False,
            protac_size_warning=False,
            high_logp_warning=False,
            high_tpsa_warning=False,
            excessive_rotatable_bonds_warning=False,
            medicinal_chemistry_notes=[validation.error or "Invalid SMILES."],
        )
    descriptors = compute_descriptors(validation.canonical_smiles or smiles)
    protac_size_warning = descriptors.mw > 1200
    high_tpsa_warning = descriptors.tpsa > 250
    high_logp_warning = descriptors.logp > 6
    excessive_rotatable_bonds_warning = descriptors.rotatable_bonds > 25
    linker_like_warning = descriptors.rotatable_bonds >= 12 and descriptors.ring_count <= 2
    notes: list[str] = []
    if protac_size_warning:
        notes.append("MW > 1200: large PROTAC-like molecules may face permeability and developability challenges.")
    if high_tpsa_warning:
        notes.append("TPSA > 250: polar surface area may reduce passive permeability.")
    if high_logp_warning:
        notes.append("logP > 6: high lipophilicity may increase nonspecific binding or toxicity risk.")
    if excessive_rotatable_bonds_warning:
        notes.append("Rotatable bonds > 25: high flexibility may reduce oral exposure and increase entropic cost.")
    if linker_like_warning:
        notes.append("High flexibility with limited ring content suggests linker-like behavior; do not reject automatically.")
    if not notes:
        notes.append("No PROTAC-aware descriptor warning thresholds were exceeded.")
    return ProtacComponentAnalysis(
        full_smiles=smiles,
        canonical_smiles=validation.canonical_smiles,
        valid=True,
        mw=descriptors.mw,
        tpsa=descriptors.tpsa,
        logp=descriptors.logp,
        hbd=descriptors.hbd,
        hba=descriptors.hba,
        rotatable_bonds=descriptors.rotatable_bonds,
        linker_like_warning=linker_like_warning,
        protac_size_warning=protac_size_warning,
        high_logp_warning=high_logp_warning,
        high_tpsa_warning=high_tpsa_warning,
        excessive_rotatable_bonds_warning=excessive_rotatable_bonds_warning,
        medicinal_chemistry_notes=notes,
    )


def batch_validate_smiles(smiles_list: list[str]) -> list[ChemicalValidationResult]:
    return [validate_smiles(smiles) for smiles in smiles_list]


def batch_compute_descriptors(smiles_list: list[str]) -> list[DescriptorResult]:
    return [compute_descriptors(smiles) for smiles in smiles_list]


def to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return dict(value)
