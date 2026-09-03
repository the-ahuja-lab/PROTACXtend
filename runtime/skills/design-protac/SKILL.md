# Design Protac

Description: Design PROTAC candidates for target/E3. Handles typed objective -> pxt_workflow; keeps candidates/run state for follow-ups.

## Trigger
Natural-language requests that match this description should use this skill automatically — the user never needs to name it.

## Steps
1. Inspect session/project state (target, E3, run_id, candidates).
2. Use pxt / pxt_catalog for evidence; pxt_workflow only for design requests.
3. Label all outputs by evidence type; keep provenance.
