# Pi integration

- Load: `pi -e runtime/src/index.ts`
- Shared model config: Pi model selection is independent; PROTACXtend's own
  backend model lives in `~/.protacxtend/llm.json` (set via
  `protacxtend llm setup`) and is read by the Python worker/graph.
- Slash + tools: `pxt`, `pxt_catalog`, `pxt_workflow`, `/pxt`.
- Persona: `runtime/prompts/protacxtend.md` (load into project rules/prompts).
- Skills: copy `runtime/skills/*/SKILL.md` into your Pi skills dir or keep as
  the project skill pack; routing wiring is slice K.
