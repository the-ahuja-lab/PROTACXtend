# Tool registry

Central catalogue: `protacxtend/agentic/registry.py` (also mirrors the Pi
`pxt`/`pxt_catalog` surface). Spec fields: name, category, description,
inputs, outputs, evidence type, readiness, deterministic/ml/surrogate/
retrieved, limitations (+ planned cost/latency/network/approval in slice I).

Groups: RESEARCH, TARGET/BIOLOGY, CHEMISTRY, STRUCTURE, DEGRADATION
(prediction), DECISION, WORKFLOW (`run_protac_design_workflow` = handoff).
Ready adapters execute real calls; `readiness="planned"` tools are hidden from
the model and rejected with an explicit error if called.
