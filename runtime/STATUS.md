# PROTACXtend Runtime — architecture, migration matrix, and current status

> Status snapshot: **slice A–E implemented & tested** (Pi extension + shared
> config + persistent Python worker + real tools + typed workflow handoff).
> Live per-node graph streaming, artifact store, coding-agent tools, env
> manager and full subagent/skill routing are the remaining slices (see
> matrix). The existing deterministic graph and Python chat REPL are intact.

## Architecture

```
User
 └─ Pi / pi-tui  (runtime/src/index.ts — pi agent loop is authoritative)
      ├─ /pxt · pxt / pxt_catalog / pxt_workflow
      ├─ persistent Python worker  (python -m protacxtend.runtime_worker)
      │      JSONL request/response — ONE worker per session, no per-call spawn
      ├─ PROTACXtend tool registry  (protacxtend/agentic/registry.py)
      ├─ Python scientific backend  (protacxtend.* tools + models)
      ├─ optional governed LangGraph workflow (typed DesignObjective → SynGlue)
      ├─ stream observations / events
      ├─ session + artifacts (slice G/H: ~/.protacxtend/…)
      └─ continue until objective complete
```

## 24-item matrix

| # | Item | Status |
|---|------|--------|
| 1 | Pi runtime scaffold | ✅ `runtime/` (extension, typechecked against Pi 0.84.4) |
| 2 | Production entrypoint | 🔶 `pi -e runtime/src/index.ts`; `PROTACXtend` shell alias pending (slice E) |
| 3 | Persistent Python bridge | ✅ `runtime_worker.py` + `src/python.ts` (tested, 6 pass/1 slow-skip) |
| 4 | True streaming | 🔶 tool events now; LangGraph `astream` per-node streaming = slice F |
| 5 | Persistent project/session | 🔶 worker session.save/list/resume JSONL exists; full project/run store = slice G |
| 6 | Artifact-first execution | ⬜ slice H (`outputs/<project>/<run>/…` with lineage) |
| 7 | General coding tools | ✅ available via Pi built-ins (read/write/bash/git); no override needed |
| 8 | Controlled dependency manager | ⬜ slice L (policy file + environment.lock sketched in docs) |
| 9 | Tool discovery | ✅ `pxt_catalog` + Python `catalog`; dynamic activation next |
| 10 | Scientific tool groups | 🔶 registry declares all groups; ready subset live, rest hidden |
| 11 | Subagents | 🔶 personas written (`runtime/agents`); delegation wiring = slice J |
| 12 | Skills | 🔶 SKILL.md x9 in `runtime/skills`; routing into sessions = slice K |
| 13 | Observation loop | ✅ strict; hallucinations rejected (tests) |
| 14 | Error → diagnose → retry | ✅ worker errors surface; agent-level recovery loop pending polish |
| 15 | Model tiers | 🔶 shared config single-model; router/synthesis split next |
| 16 | Human/capability policy | ⬜ policy doc written (`docs/PERMISSIONS.md`); Pi gate hooks slice |
| 17 | TUI experience | ✅ Pi TUI is the runtime; header/status customization partial |
| 18 | Chat follow-up behaviour | 🔶 Python agent session-context reuse; project-state reuse = slice G |
| 19 | LangGraph role | ✅ preserved — Pi decides, graph stays authoritative for design |
| 20 | Acceptance test | 🔶 end-to-end works for tools + workflow; resume test = slice G |
| 21 | Tests | ✅ worker+protocol 6/7, conversational 9/9; Pi startup/TUI tests next |
| 22 | Documentation | 🔶 created under `docs/` (architecture, PI integration, sessions/artifacts, registry, env manager, permissions, subagents, skills) |
| 23 | Migration order | A–E done; F(G,H) next; Python REPL stays until full acceptance |
| 24 | Final report | 🔶 this file + per-slice reports in PRs |

## Verified in this session

- `protacxtend/runtime_worker.py` JSONL protocol: ping/catalog/tool/session
  (6 passed, 1 slow graph test opt-in).
- `runtime/tests/bridge-smoke.mjs`: real `inspect_smiles` call through the
  persistent worker → `success · CALCULATED`, fake tool rejected, session save/
  resume OK.
- `runtime/src/index.ts` typechecks clean against `@earendil-works/pi-coding-agent` 0.84.4.
- Conversational agent tests still green (9/9) — nothing regressed.

## How to run the Pi slice

```bash
cd runtime && npm install
# shared LLM config (API vs Ollama) still comes from protacxtend llm setup
pi -e src/index.ts
# inside Pi:  "research BRD4 as a degradation target" → pxt tools
#             "design 10 CRBN PROTACs for BRD4"        → pxt_workflow
```

Next increments (in order): **F** LangGraph live streaming → **G** project/
session store (`/save /resume /sessions /projects`, `--resume`) → **H**
artifact-first outputs → **I** env manager → **J/K** subagent + skill routing →
**L** full policy gates → full acceptance run.
