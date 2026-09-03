# PROTACXtend Conversational Agent Architecture

Status: **working vertical slice** (v0.3 conversational layer). This document
describes the layered design — the conversational agent sits **above** the
deterministic scientific graph and never replaces it.

```
USER
 └─> Node/pi TUI ──protacxtend chat / tui──┐
                                            ▼
                             CONVERSATIONAL LLM AGENT
                             (protacxtend/agentic/chat_agent.py)
                                │  intent · planning · tool selection
                                ▼
                             STRICT TOOL REGISTRY
                             (protacxtend/agentic/registry.py)
                                │  observations / evidence (ToolResult)
                                ▼
                        need full design workflow?
                           ├─ no  → evidence-grounded answer
                           └─ yes
                                 ▼
                         typed DesignObjective
                         (protacxtend/agentic/contract.py)
                                 ▼
                         human/safety gate
                                 ▼
                         deterministic SynGlue graph
                         (backend.main.run_workflow_from_request)
                                 ▼
                         events → chat → ranked candidates + report
```

## 1. Shared LLM configuration (single source of truth)

- Persisted choice: `~/.protacxtend/llm.json` (0600) — written by
  `protacxtend llm setup` (interactive “API or Ollama?”), or by flags
  `protacxtend llm --provider ... --model ... --base-url ...`.
- Read order in `protacxtend/llm/providers.py#get_config`:
  **runtime override → env (`PROTACPILOT_LLM_*`) → saved file → defaults**.
- One config feeds: chat agent, LangGraph decision layer, backend API,
  TUI model status, one-shot `protacxtend chat`, `run --llm-enabled`.

## 2. Conversational agent loop

`ConversationalAgent.turn()` iterates (max 10 steps). At each step the model
receives: system contract, tool catalog, conversation tail, session context
(previous objective/run), and compact tool observations. The model returns a
JSON action — validated before any execution:

- `tool_call` — name must exist **and** have `readiness="ready"` in the
  registry; otherwise the call is rejected and the model is re-prompted
  (nothing is ever executed silently).
- `workflow_handoff` — only when a design/run is requested; produces a typed
  `DesignObjective`.
- `clarification` — human gate; chat surfaces `ACTION REQUIRED` and asks.
- `final_answer` — labelled with evidence types.

Tool observations are compacted (no giant raw dumps) — cost control.

## 3. Tool registry

`protacxtend/agentic/registry.py` is the single catalogue. Every entry has
purpose, inputs, evidence type, limitations, readiness, and whether it is
deterministic / ML / surrogate / retrieved. **Ready tools are actually
executed** (Europe PMC, PubMed E-utilities, CrossRef, UniProt, ChEMBL REST,
local E3 evidence, RDKit SMILES inspection). Tools with `readiness="planned"`
are never advertised to the model and return an explicit error if called —
they are visible in `/tools` for the roadmap only. ToolResult schema:

```json
{ "tool": "...", "status": "success|warning|error", "summary": "...",
  "data": {}, "sources": [], "confidence": null, "model_version": null,
  "evidence_type": "RETRIEVED|CALCULATED|ML PREDICTION|STRUCTURAL SURROGATE|HEURISTIC|USER INPUT|NOT AVAILABLE",
  "limitations": [], "warnings": [] }
```

## 4. Chat → graph handoff

When the user asks for a candidate workflow, the agent returns a typed
`DesignObjective` (target, E3, objectives, constraints, candidates, cell
line). The objective is kept typed in chat memory/provenance and rendered to a
**canonical request sentence** because the underlying SynGlue entry currently
parses natural language (`run_workflow_from_request`); internal graph state is
typed. Follow-up turns reuse `last_objective`, `run_id`, and the summary so
the user never has to repeat target/E3.

## 5. Streaming events / human gates / honesty

- `AgentEvent` renders as `[kind] action · tool (status) → summary` — never
  chain-of-thought.
- Human gates: clarification actions interrupt for user input; graph launch
  emits a gate event; the deterministic graph’s own human gates remain.
- Response contract: evidence labels are preserved from tool results; the LLM
  is instructed never to upgrade surrogate/feasibility outputs into measured
  quantities.

## 6. Commands

```bash
protacxtend llm setup                      # API vs Ollama (first-run question)
protacxtend chat                           # pi-style REPL
protacxtend chat "question..."             # one-shot
protacxtend run "Design ..." --llm-enabled # existing gated graph (same config)
```

`/llm`, `/model set NAME`, `/models`, `/tools`, `/agents`, `/run`,
`/status`, `/clear`, `/help`, `/exit` inside the REPL.

## 7. Tests

`protacxtend/tests/test_conversational_agent.py` covers: factual (tools, no
graph), comparison, typed handoff, follow-up state reuse, visible tool
failure, hallucinated-tool rejection, clarification gate, shared config file,
and registry readiness filtering (9 tests).

## 8. Known limitations (next increments)

- Node/pi TUI: the REPL is currently the Python `protacxtend chat`; wiring the
  Node `tui/` startup prompt + streaming events into `app.ts` is the next
  slice.
- Only the ready subset of the registry is live; prediction/ranking/dossier
  adapters are `planned` (the full graph still provides those outputs).
- Graph run events are aggregated post-run (no per-node `astream` hook yet).
- Model cost tiers (cheap router vs strong synthesizer) are not yet
  implemented — single configured model today.
