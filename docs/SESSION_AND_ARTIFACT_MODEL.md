# Session & artifact model (slice G/H design)

Layout (created under ~/.protacxtend or PROTACXTEND_HOME):

projects/ sessions/ runs/ evidence/ artifacts/ cache/ environments/ models/ logs/

Persist per run: objective, plan, target/E3/cell line, constraints, tool
observations, evidence references, warheads/linkers/candidate ids, predictions,
ternary results, OOD flags, rejections, user decisions, workflow checkpoints,
artifacts. Sessions store science context, not just chat. Artifact layout:
outputs/<project>/<run_id>/{objective.json, session.json, evidence.jsonl,
sources.json, candidate_table.csv, predictions.csv, ranking.csv,
provenance.jsonl, warnings.json, structures/, plots/, code/, final_report.md}.
Every artifact carries lineage (tool/model/input/run).

Current: worker session.save/list/resume (JSONL) verified. Full project store,
`/save /resume /sessions /projects` and `--resume` = slice G.
