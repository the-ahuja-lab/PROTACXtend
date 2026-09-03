# PROTACXTEND Runtime Architecture

```
User
 └─ Pi / pi-tui            (runtime/src/index.ts)  ← agent loop is Pi's
      ├─ pxt · pxt_catalog · pxt_workflow · /pxt
      ├─ persistent Python worker (JSONL, one per session)
      │    protacxtend/runtime_worker.py
      ├─ PROTACXtend tool registry → real adapters (EPMC, PubMed, Crossref,
      │    UniProt, ChEMBL, E3, RDKit …)  + typed DesignObjective
      ├─ Python scientific backend (unchanged, authoritative)
      ├─ optional governed LangGraph/SynGlue workflow
      ├─ observations/events → session/artifacts (~/.protacxtend/…)
```

Non-negotiables: deterministic graph is never replaced; no per-call Python
spawn; no fabricated tool results; evidence labels preserved end-to-end.
Detailed matrix + status: `runtime/STATUS.md`.
