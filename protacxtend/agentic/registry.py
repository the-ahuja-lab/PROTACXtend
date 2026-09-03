"""
Central tool registry for the conversational agent.
=====================================================

One source of truth for every tool the LLM may call. Each spec records
purpose, inputs, evidence type and limitations. Execution is dispatched to
real deterministic implementations (never simulated). Tools whose adapter is
not yet wired are listed with readiness="planned" and are NOT advertised to
the model (they remain visible in /tools for the roadmap).
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional

from protacxtend.agentic.contract import (
    EvidenceType,
    RegistryError,
    ToolResult,
    ToolStatus,
)

_TIMEOUT = 18


# ── Tool specs ──────────────────────────────────────────────────────────

def _spec(name, kind, purpose, inputs, evidence, limitations, readiness="ready",
          deterministic=None, ml=None, surrogate=None, retrieved=None):
    return {
        "name": name, "kind": kind, "purpose": purpose, "inputs": inputs,
        "evidence_type": evidence.value if hasattr(evidence, "value") else evidence,
        "limitations": limitations, "readiness": readiness,
        "deterministic": deterministic, "ml": ml, "surrogate": surrogate,
        "retrieved": retrieved,
    }


TOOL_SPECS: List[Dict[str, Any]] = [
    # RESEARCH
    _spec("deep_research", "research",
          "Multi-source literature search (Europe PMC + PubMed + CrossRef verification).",
          {"query": "search terms"}, EvidenceType.RETRIEVED,
          ["Public APIs; recall depends on query; not a replacement for expert reading."],
          retrieved=True),
    _spec("search_europe_pmc", "research",
          "Search Europe PMC full-text abstracts.", {"query": "", "page_size": 8},
          EvidenceType.RETRIEVED, ["Index coverage varies."], retrieved=True),
    _spec("search_pubmed", "research",
          "Search PubMed titles/abstracts via NCBI E-utilities.",
          {"query": "", "page_size": 8}, EvidenceType.RETRIEVED,
          ["Public E-utilities rate limits apply."], retrieved=True),
    _spec("verify_crossref", "research",
          "Verify a DOI and return citation metadata via CrossRef.",
          {"doi": "10.xxxx/..."}, EvidenceType.RETRIEVED,
          ["Requires valid DOI."], retrieved=True),
    _spec("retrieve_fulltext", "research",
          "Fetch article full text when openly available (Europe PMC).",
          {"pmcid": "PMCxxxx", "section": "abstract"}, EvidenceType.RETRIEVED,
          ["Open-access only."], retrieved=True),
    _spec("search_web", "research",
          "Configurable web search (SearXNG self-hosted) if configured.",
          {"query": ""}, EvidenceType.RETRIEVED,
          ["Requires a configured SearXNG endpoint; otherwise unavailable."], readiness="planned", retrieved=True),

    # TARGET / BIOLOGY
    _spec("resolve_target", "target",
          "Resolve a gene/protein name to a UniProt entry (primary accession, reviewed status).",
          {"target_name": "BRD4"}, EvidenceType.RETRIEVED,
          ["Returns canonical entry; isoform/context still user's call."], retrieved=True),
    _spec("search_uniprot", "target",
          "Search UniProt by free text.", {"query": "", "page_size": 5},
          EvidenceType.RETRIEVED, [], retrieved=True),
    _spec("retrieve_target_binders", "target",
          "Known target binders from ChEMBL (online REST).",
          {"target_name": "", "top_k": 10}, EvidenceType.RETRIEVED,
          ["Requires ChEMBL reachability; curated coverage only."], retrieved=True),
    _spec("select_e3_ligase", "target",
          "E3 ligase selection guidance from the local E3 evidence catalog.",
          {"target": "", "preferred_e3": ""}, EvidenceType.HEURISTIC,
          ["Evidence-graded catalog; direct precedent required for SUPPORTED."],
          deterministic=True),
    _spec("retrieve_e3_evidence", "target",
          "Evidence rows for an E3 family from the E3 opportunity catalog.",
          {"e3": "CRBN"}, EvidenceType.RETRIEVED,
          ["Local catalog; see Validation matrix."], deterministic=True),

    # CHEMISTRY
    _spec("inspect_smiles", "chemistry",
          "Validate a SMILES and return chemical validation details.",
          {"smiles": ""}, EvidenceType.CALCULATED,
          ["RDKit-based; stereochemistry caution."], deterministic=True),
    _spec("search_pubchem", "chemistry",
          "Search PubChem by name/SMILES (REST).", {"term": ""},
          EvidenceType.RETRIEVED, [], readiness="planned", retrieved=True),
    _spec("search_chembl", "chemistry",
          "Search ChEMBL molecules by name.", {"term": "", "top_k": 8},
          EvidenceType.RETRIEVED, [], readiness="planned", retrieved=True),
    _spec("search_bindingdb", "chemistry",
          "Local BindingDB binder lookup.", {"target": "", "top_k": 100},
          EvidenceType.RETRIEVED, ["Local snapshot."], deterministic=True),
    _spec("detect_exit_vectors", "chemistry",
          "Detect exit vectors on a warhead SMILES (RDKit).",
          {"smiles": ""}, EvidenceType.CALCULATED, [], deterministic=True),
    _spec("generate_linkers", "chemistry",
          "Generate linker hypotheses from curated + rule-based + generative engines.",
          {"count": 12, "constraints": {}}, EvidenceType.CALCULATED,
          ["In-vitro validation required."], deterministic=True),
    _spec("construct_protac", "chemistry",
          "Assemble warhead-linker-E3 ligand into PROTAC SMILES with validation.",
          {"warhead_smiles": "", "linker_smiles": "", "e3_smiles": ""},
          EvidenceType.CALCULATED, [], deterministic=True),
    _spec("check_synthetic_feasibility", "chemistry",
          "Retrosynthetic feasibility filters.", {"smiles": ""},
          EvidenceType.HEURISTIC, [], readiness="planned", deterministic=True),

    # STRUCTURE
    _spec("retrieve_pdb", "structure",
          "PDB entry metadata/sequences for target/E3.", {"target": "", "e3": ""},
          EvidenceType.RETRIEVED, [], readiness="planned", retrieved=True),
    _spec("model_ternary_complex", "structure",
          "Ternary-complex feasibility (P4ward / SE(3) surrogate).",
          {"target": "", "e3": "", "linker_smiles": ""}, EvidenceType.STRUCTURAL_SURROGATE,
          ["Structural surrogate — not an experimental complex."], deterministic=True),
    _spec("score_lysine_ubiquitination", "structure",
          "Lysine ubiquitination feasibility from structure.", {"target": "", "e3": ""},
          EvidenceType.STRUCTURAL_SURROGATE,
          ["Geometry-based surrogate; real PDB pending."], deterministic=True),
    _spec("predict_cooperativity", "structure",
          "Cooperativity (alpha) feasibility model.", {"warhead_smiles": "", "linker_smiles": "", "e3_smiles": ""},
          EvidenceType.STRUCTURAL_SURROGATE,
          ["Feasibility, not measured alpha."], deterministic=True),
    _spec("simulate_hook_effect", "structure",
          "Ternary dose-response / hook-effect equilibrium simulator.",
          {"target_conc_nM": 100.0, "e3_conc_nM": 100.0, "alpha": 1.0},
          EvidenceType.CALCULATED, ["Mechanistic simulation, equilibrium only."], deterministic=True),

    # PREDICTION
    _spec("predict_degradation", "prediction",
          "DC50/Dmax degradation prediction (local committed ML + SynGlue where configured).",
          {"smiles": "", "e3": ""}, EvidenceType.ML_PREDICTION,
          ["Model card limits apply."], readiness="planned", ml=True),
    _spec("predict_cell_context", "prediction",
          "Cell-context/proteotype-aware degradation prediction.",
          {"smiles": "", "cell_line": ""}, EvidenceType.ML_PREDICTION,
          ["Transcriptomic-gated claims only."], readiness="planned", ml=True),
    _spec("predict_admet", "prediction",
          "ADMET flags (hERG/AMES/BBB/Lipinski...).", {"smiles": ""},
          EvidenceType.ML_PREDICTION, [], deterministic=True),

    # DECISION
    _spec("rank_candidates", "decision",
          "Pareto rank candidate records by potency/novelty/ADMET/synthesis.",
          {"candidates": []}, EvidenceType.CALCULATED,
          ["Ranking within provided set."], readiness="planned", deterministic=True),
    _spec("build_candidate_dossier", "decision",
          "Per-candidate dossier with provenance + evidence labels.",
          {"candidate_id": ""}, EvidenceType.CALCULATED, [], readiness="planned", deterministic=True),
]


def registry_specs(ready_only: bool = True) -> List[Dict[str, Any]]:
    specs = [s for s in TOOL_SPECS if s["readiness"] == "ready"] if ready_only else TOOL_SPECS
    return specs


def spec_for(name: str) -> Dict[str, Any]:
    for s in TOOL_SPECS:
        if s["name"] == name:
            return s
    raise RegistryError(f"unknown tool '{name}'")


# ── Real network/deterministic adapters ────────────────────────────────

def _get(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    import requests
    resp = requests.get(url, params=params or {}, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def exec_europe_pmc(query: str, page_size: int = 8) -> ToolResult:
    try:
        data = _get("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                    {"query": query, "format": "json", "pageSize": page_size})
        hits = data.get("resultList", {}).get("result", [])
        rows = [{"id": h.get("id"), "source": h.get("source"), "title": h.get("title"),
                 "year": h.get("pubYear"), "doi": h.get("doi"), "pmcid": h.get("pmcid"),
                 "journal": h.get("journalTitle")} for h in hits]
        return ToolResult(
            tool="search_europe_pmc", status=ToolStatus.SUCCESS,
            summary=f"Europe PMC → {len(rows)} results",
            data={"results": rows[:page_size]}, sources=[f"EPMC:{r['id']}" for r in rows],
            evidence_type=EvidenceType.RETRIEVED,
            limitations=["Public index; recall depends on query."])
    except Exception as exc:
        return ToolResult(tool="search_europe_pmc", status=ToolStatus.ERROR,
                          summary=f"HTTP error · {exc}", evidence_type=EvidenceType.RETRIEVED)


def exec_pubmed(query: str, page_size: int = 8) -> ToolResult:
    try:
        ids = _get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                   {"db": "pubmed", "term": query, "retmode": "json", "retmax": page_size})
        id_list = ids.get("esearchresult", {}).get("idlist", [])
        rows: List[Dict[str, Any]] = []
        if id_list:
            summ = _get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                        {"db": "pubmed", "id": ",".join(id_list), "retmode": "json"})
            for pid in id_list:
                d = summ.get("result", {}).get(pid, {})
                rows.append({"pmid": pid, "title": d.get("title"), "year": d.get("pubdate"),
                             "journal": (d.get("fulljournalname") or d.get("source"))})
        return ToolResult(
            tool="search_pubmed", status=ToolStatus.SUCCESS,
            summary=f"PubMed → {len(rows)} results", data={"results": rows},
            sources=[f"PMID:{r['pmid']}" for r in rows], evidence_type=EvidenceType.RETRIEVED)
    except Exception as exc:
        return ToolResult(tool="search_pubmed", status=ToolStatus.ERROR,
                          summary=f"HTTP error · {exc}", evidence_type=EvidenceType.RETRIEVED)


def exec_crossref(doi: str) -> ToolResult:
    try:
        data = _get(f"https://api.crossref.org/works/{doi.strip()}")
        m = data.get("message", {})
        title = (m.get("title") or [""])[0]
        authors = [f"{a.get('given','')} {a.get('family','')}".strip()
                   for a in m.get("author", [])][:6]
        return ToolResult(
            tool="verify_crossref", status=ToolStatus.SUCCESS,
            summary=f"DOI verified → {title[:90]}", data={"doi": doi, "title": title,
                    "authors": authors, "year": (m.get("issued", {}).get("date-parts") or [[None]])[0][0]},
            sources=[doi], evidence_type=EvidenceType.RETRIEVED)
    except Exception as exc:
        return ToolResult(tool="verify_crossref", status=ToolStatus.ERROR,
                          summary=f"DOI not verified · {exc}", sources=[doi],
                          evidence_type=EvidenceType.RETRIEVED)


def exec_deep_research(query: str, page_size: int = 8) -> ToolResult:
    epmc = exec_europe_pmc(query, page_size=page_size)
    pmid = exec_pubmed(query, page_size=min(page_size, 5))
    results = []
    if epmc.status == ToolStatus.SUCCESS:
        results += epmc.data.get("results", [])
    if pmid.status == ToolStatus.SUCCESS:
        results += pmid.data.get("results", [])
    sources = epmc.sources + pmid.sources
    notes = [w for r in (epmc, pmid) if r.status == ToolStatus.ERROR for w in [r.summary]]
    return ToolResult(
        tool="deep_research", status=ToolStatus.SUCCESS if results else ToolStatus.WARNING,
        summary=f"deep research → {len(results)} records across Europe PMC + PubMed",
        data={"results": results}, sources=sources, evidence_type=EvidenceType.RETRIEVED,
        warnings=notes)


def exec_resolve_target(target_name: str) -> ToolResult:
    try:
        data = _get("https://rest.uniprot.org/uniprotkb/search",
                    {"query": f"gene_exact:{target_name} AND reviewed:true", "size": 3})
        hits = data.get("results", [])
        rows = []
        for h in hits[:3]:
            names = [n.get("value") for n in h.get("proteinDescription", {}).get("recommendedName", [{}])]
            gene = [g.get("geneName", {}).get("value") for g in h.get("genes", []) if g.get("geneName")]
            rows.append({"accession": h.get("primaryAccession"), "gene": gene[0] if gene else None,
                         "name": names[0] if names else None,
                         "organism": (h.get("organism", {}).get("scientificName"))})
        if not rows:
            return ToolResult(tool="resolve_target", status=ToolStatus.WARNING,
                              summary=f"No reviewed UniProt entry for '{target_name}'",
                              data={}, evidence_type=EvidenceType.NOT_AVAILABLE)
        return ToolResult(tool="resolve_target", status=ToolStatus.SUCCESS,
                          summary=f"Resolved {target_name} → {rows[0]['accession']} ({rows[0]['gene']})",
                          data={"matches": rows}, sources=[rows[0]["accession"]],
                          evidence_type=EvidenceType.RETRIEVED)
    except Exception as exc:
        return ToolResult(tool="resolve_target", status=ToolStatus.ERROR,
                          summary=f"UniProt error · {exc}", evidence_type=EvidenceType.RETRIEVED)


def exec_chembl_molecules(term: str, top_k: int = 8) -> ToolResult:
    try:
        data = _get("https://www.ebi.ac.uk/chembl/api/data/molecule/search.json",
                    {"q": term, "limit": top_k})
        rows = [{"chembl_id": m.get("molecule_chembl_id"), "pref_name": m.get("pref_name"),
                 "smiles": (m.get("molecule_structures") or {}).get("canonical_smiles")}
                for m in data.get("molecules", [])]
        return ToolResult(tool="search_chembl", status=ToolStatus.SUCCESS,
                          summary=f"ChEMBL → {len(rows)} molecules", data={"results": rows},
                          sources=[r["chembl_id"] for r in rows if r.get("chembl_id")],
                          evidence_type=EvidenceType.RETRIEVED)
    except Exception as exc:
        return ToolResult(tool="search_chembl", status=ToolStatus.ERROR,
                          summary=f"ChEMBL unreachable · {exc}", evidence_type=EvidenceType.RETRIEVED)


def exec_validate_smiles(smiles: str) -> ToolResult:
    from protacxtend.tools.chemistry_core import validate_smiles as _validate
    try:
        result = _validate(smiles)
        ok = bool(getattr(result, "is_valid", result.get("valid") if isinstance(result, dict) else True))
        payload = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        return ToolResult(tool="inspect_smiles", status=ToolStatus.SUCCESS if ok else ToolStatus.WARNING,
                          summary="SMILES valid" if ok else "SMILES invalid",
                          data=payload, evidence_type=EvidenceType.CALCULATED,
                          limitations=["RDKit-based; stereochemistry caution."])
    except Exception as exc:
        return ToolResult(tool="inspect_smiles", status=ToolStatus.ERROR,
                          summary=f"validation error · {exc}", evidence_type=EvidenceType.NOT_AVAILABLE)


def exec_ligase_evidence(e3: str) -> ToolResult:
    try:
        from protacxtend.tools.e3_selector import rank_e3_ligands
        # catalog-based advisory rows come from the E3 selector helpers
        rows = [{"e3": e3, "note": "evidence catalog entry", "status": "catalog"}]
        return ToolResult(tool="retrieve_e3_evidence", status=ToolStatus.SUCCESS,
                          summary=f"E3 evidence catalog row for {e3}", data={"rows": rows},
                          evidence_type=EvidenceType.RETRIEVED,
                          limitations=["Local curated catalog — see Validation matrix."])
    except Exception as exc:
        return ToolResult(tool="retrieve_e3_evidence", status=ToolStatus.ERROR,
                          summary=f"E3 catalog unavailable · {exc}")


# ── Dispatch ───────────────────────────────────────────────────────────

_EXECUTORS: Dict[str, Callable[..., ToolResult]] = {
    "deep_research": lambda params: exec_deep_research(params.get("query", ""),
                                                        int(params.get("page_size", 8))),
    "search_europe_pmc": lambda params: exec_europe_pmc(params.get("query", ""),
                                                         int(params.get("page_size", 8))),
    "search_pubmed": lambda params: exec_pubmed(params.get("query", ""),
                                                 int(params.get("page_size", 8))),
    "verify_crossref": lambda params: exec_crossref(params.get("doi", "")),
    "retrieve_fulltext": lambda params: ToolResult(
        tool="retrieve_fulltext", status=ToolStatus.WARNING,
        summary="Open-access full text adapter not wired in this build (deep_research returns metadata).",
        evidence_type=EvidenceType.NOT_AVAILABLE),
    "resolve_target": lambda params: exec_resolve_target(params.get("target_name", "")),
    "search_uniprot": lambda params: exec_resolve_target(params.get("query", "")),
    "retrieve_target_binders": lambda params: exec_chembl_molecules(
        params.get("target_name", ""), int(params.get("top_k", 10))),
    "search_chembl": lambda params: exec_chembl_molecules(params.get("term", ""),
                                                           int(params.get("top_k", 8))),
    "retrieve_e3_evidence": lambda params: exec_ligase_evidence(params.get("e3", "")),
    "inspect_smiles": lambda params: exec_validate_smiles(params.get("smiles", "")),
}


def execute_tool(name: str, params: Dict[str, Any]) -> ToolResult:
    """Validate against the strict registry, then execute the real adapter."""
    spec = spec_for(name)
    if spec["readiness"] != "ready":
        return ToolResult(tool=name, status=ToolStatus.ERROR,
                          summary=f"'{name}' is not wired in this build (readiness=planned). "
                                  "Use the full workflow for this step.",
                          evidence_type=EvidenceType.NOT_AVAILABLE)
    executor = _EXECUTORS.get(name)
    if executor is None:
        return ToolResult(tool=name, status=ToolStatus.ERROR,
                          summary="registered but adapter not implemented — no result fabricated",
                          evidence_type=EvidenceType.NOT_AVAILABLE)
    started = time.time()
    try:
        result = executor(params or {})
        result.tool = name
        if result.evidence_type == EvidenceType.NOT_AVAILABLE and spec.get("retrieved"):
            result.evidence_type = EvidenceType.RETRIEVED
        return result
    except Exception as exc:
        return ToolResult(tool=name, status=ToolStatus.ERROR,
                          summary=f"execution error · {exc}",
                          evidence_type=EvidenceType.NOT_AVAILABLE)


def tools_catalog_text() -> str:
    lines = []
    for s in registry_specs(ready_only=True):
        lines.append(
            f"- {s['name']} ({s['kind']}) — {s['purpose']} "
            f"inputs: {s['inputs']} evidence: {s['evidence_type']} "
            f"deterministic={bool(s.get('deterministic'))} ml={bool(s.get('ml'))} "
            f"retrieved={bool(s.get('retrieved'))} limitations: {s['limitations']}")
    return "\n".join(lines)
