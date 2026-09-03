# @protacxtend/runtime

Pi runtime for PROTACXtend. Loads a persistent Python science worker and
exposes registered scientific tools + governed-workflow handoff as Pi tools.

Run:
  pi -e runtime/src/index.ts          # interactive Pi session with pxt tools
  PROTACXTEND  →  pi alias / launcher (see docs/PROTACXTEND_RUNTIME_ARCHITECTURE.md)

Commands/tools: pxt, pxt_catalog, pxt_workflow, /pxt, /save /resume (slice G+).
See runtime/STATUS.md for the full migration matrix.
