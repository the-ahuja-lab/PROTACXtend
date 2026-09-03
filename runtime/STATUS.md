# PROTACXtend Runtime — architecture, migration matrix, and current status

> Status snapshot: **E, F, G, H implemented and tested** — STOP GATE reached.
> Next slices (I–L: coding-tool audit, subagents, skills routing, env manager,
> full policy gates) must NOT start until this checkpoint is audited.
> The existing deterministic graph and Python chat REPL remain intact.

## Architecture

```
User
 └─ PROTACXtend  (pi_launcher → pi -e runtime/src/index.ts — Pi loop authoritative)
      ├─ pxt · pxt_catalog · pxt_workflow · /pxt
      ├─ persistent Python worker (JSONL) — protacxtend/runtime_worker.py
      │    ├─ tools → strict registry → real adapters
      │    └─ workflow → agents/stream.py → LangGraph astream (live node events)
      │                       └─→ deterministic SynGlue graph (authoritative)
      ├─ state store (~/.protacxtend): projects/ sessions/ runs/ outputs/ …
      ├─ artifact store (outputs/<project>/<run>/ + provenance.jsonl lineage)
      └─ continue until objective complete
```

## 24-item matrix (states: COMPLETE / PARTIAL / NOT STARTED / BLOCKED)

| # | Item | State | Notes |
|---|------|-------|-------|
| 1 | Pi runtime scaffold | COMPLETE | `runtime/`, typechecked vs Pi 0.84.4 |
| 2 | Production entrypoint | COMPLETE | `PROTACXtend` → pi TUI proven from repo root AND `CLI/` (π v0.84.4; terminal title “π - CLI” ⇒ cwd preserved); `PROTACXtend runtime status` prints full READY report |
| 3 | Persistent Python bridge | COMPLETE | worker JSONL ping/catalog/tool/workflow/session.* (tests) |
| 4 | True LangGraph streaming | COMPLETE | `agents/stream.py` astream `updates+values`; node events real; tests show intermediate event before complete |
| 5 | Persistent project/session store | COMPLETE | `state/store.py` projects/sessions/runs; save/list/resume tests incl. restart |
| 6 | Artifact-first execution | COMPLETE | `state/artifacts.py` writes layout + provenance; metadata/checksum/lineage tests |
| 7 | General coding tools | PARTIAL | Pi built-ins only; audit+expose deferred to slice I (per stop gate) |
| 8 | Controlled dependency manager | NOT STARTED | slice I (after checkpoint) |
| 9 | Tool discovery | COMPLETE | `pxt_catalog` + worker catalog (20 ready tools) |
| 10 | Scientific tool groups | COMPLETE (registry) / PARTIAL (adapters) | planned groups hidden; adapters ready subset |
| 11 | Subagents | PARTIAL | personas in `runtime/agents`; delegation = slice J |
| 12 | Skills | PARTIAL | SKILL.md ×9 in `runtime/skills`; routing = slice K |
| 13 | Observation loop | COMPLETE | hallucination rejected (tests) |
| 14 | Error → diagnose → retry | PARTIAL | errors surfaced; agent-level recovery polish pending |
| 15 | Model tiers | PARTIAL | single shared config; router/synthesis split pending |
| 16 | Capability policy | PARTIAL | docs/PERMISSIONS.md; Pi gates hook = slice L |
| 17 | TUI experience | COMPLETE | Pi TUI is runtime (banner/footer verified); header polish optional |
| 18 | Chat follow-up behaviour | PARTIAL | session-state reuse; project-level follow-up tests pass in store |
| 19 | LangGraph role | COMPLETE | preserved; Pi decides, graph authoritative |
| 20 | Acceptance test | PARTIAL | tools+launcher+store verified; full end-to-end BRD4 transcript pending manual run |
| 21 | Tests | COMPLETE (unit) | 23 passed / 1 opt-in slow; Pi+TUI runtime tests listed as pending |
| 22 | Documentation | COMPLETE | docs/* set + this file |
| 23 | Migration order | A–H done | I onward gated |
| 24 | Final report | COMPLETE | per-slice reports in PRs + this file |

## Verified in this session (slices E–H)

- **E**: launcher is installation-anchored (PROTACXTEND_ROOT or module location — never cwd); verifies package.json/src/index.ts, checks runtime deps (auto-install w/ PROTACXTEND_AUTO_SETUP=1 or clear npm action), execs `pi -e <absolute ext>` in the user’s cwd. Proven from repo root and `CLI/` in a PTY (π v0.84.4, stayed alive); `PROTACXtend runtime status` → READY. Tests launch from root/CLI//tmp/home.
- **F**: `agents/stream.py` emits real `node` events via LangGraph
  `astream(stream_mode=["updates","values"])`; test proves an intermediate
  node event precedes `workflow_complete`. No timers/simulated progress.
- **G**: store create/save/list/resume + run events; worker exposes
  `project.*` / `session_state.*`; restart (fresh store read) restores context.
- **H**: artifact metadata (id/producer/inputs/evidence/params/checksum),
  `provenance.jsonl`, lineage traversal and after-restart reads all tested.

## Acceptance demo (manual, next step)

Run on a model-configured machine:

```
PROTACXtend
  > Investigate BRD4 as a degradation target.      (pxt research tools live)
  > Design 10 CRBN PROTACs prioritizing degradation and permeability.
    (LangGraph starts; node events stream live; outputs/<BRD4_CRBN>/<run> artifacts)
  > save this as BRD4_CRBN
(exit)
PROTACXtend --resume                               (restores BRD4_CRBN)
  > Why did candidate 2 rank below candidate 1?   (reads stored ranking artifacts)
  > Show the evidence supporting candidate 1's warhead.  (lineage)
```

## Known limitations (post-checkpoint)

- Real-graph streaming verified via synthetic LangGraph test; a full heavy
  BRD4 run transcript should be recorded on a user machine (minutes-long run).
- `--resume` CLI/flag wiring into Pi + `/save /resume /sessions /projects`
  commands inside Pi are next (store/worker APIs already exist).
- Artifact content from the real graph currently = objective/run/summary JSON;
  candidate/prediction CSV writers are wired in `artifacts.py` and need the
  state→table mapping for the real run state.
