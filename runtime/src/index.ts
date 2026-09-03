/**
 * PROTACXtend Pi extension — conversational scientific runtime.
 *
 * Register with pi:  pi -e runtime/src/index.ts
 * or add this file to your pi extension list (see docs/PI_INTEGRATION.md).
 *
 * Slice A–E of the migration: shared config (Python-side), persistent Python
 * worker bridge, real tool execution and workflow handoff exposed as Pi tools.
 * Pi's own agent loop stays authoritative — nothing here re-implements it.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { PythonBridge } from "./python.ts";

let bridge: PythonBridge | null = null;

function getBridge(pi: ExtensionAPI): PythonBridge {
  if (!bridge) {
    bridge = new PythonBridge();
    bridge.on("stderr", (msg: string) => pi.sendMessage({
      customType: "pxt_worker", content: `worker: ${msg}`, display: true, details: {},
    }));
    pi.on("session_shutdown", () => { try { bridge?.close(); } catch {} bridge = null; });
  }
  return bridge;
}

function truncate(text: string, max = 12000): string {
  return text.length <= max ? text : text.slice(0, max) + "\n… (truncated)";
}

export default function (pi: ExtensionAPI) {
  // ── scientific tool passthrough (strict registry enforced in Python) ──
  pi.registerTool({
    name: "pxt",
    label: "PROTACXtend science tool",
    description:
      "Run a registered PROTACXtend scientific tool (deep_research, search_europe_pmc, " +
      "search_pubmed, verify_crossref, resolve_target, search_uniprot, search_chembl, " +
      "retrieve_e3_evidence, inspect_smiles, ...). Tool list: use pxt_catalog. " +
      "Result is real tool output with an evidence label — never fabricate.",
    promptSnippet: "Run PROTACXtend scientific tools for literature/target/chemistry questions",
    promptGuidelines: [
      "Use pxt when a scientific database, literature or SMILES question needs a real lookup; the tool runs in a persistent Python worker and returns labelled evidence.",
      "Use pxt_catalog before calling pxt if you are unsure a tool name exists.",
      "Do not narrate a lookup you did not perform with pxt.",
    ],
    parameters: Type.Object({
      tool: Type.String({ description: "Registered tool name" }),
      args: Type.Optional(Type.Record(Type.String(), Type.Any(), {
        description: "Tool arguments, e.g. { query: 'BRD4 PROTAC' }",
      })),
    }),
    async execute(_id, params, signal, onUpdate, ctx) {
      if (signal?.aborted) return { content: [{ type: "text", text: "cancelled" }], details: {} };
      const b = getBridge(pi);
      onUpdate?.({ content: [{ type: "text", text: `running ${params.tool}…` }], details: {} });
      const r = await b.call("tool", { tool: params.tool, args: params.args ?? {} });
      const label = `[${String(r.evidence_type ?? "?")}] ${params.tool} · ${String(r.status)}`;
      const text = `${label}\n${String(r.summary ?? "")}\n${truncate(JSON.stringify(r.data ?? {}, null, 2))}`;
      if (r.status === "error") throw new Error(text);
      return { content: [{ type: "text", text }], details: { ...r } };
    },
  });

  // ── catalog / discovery ───────────────────────────────────────────────
  pi.registerTool({
    name: "pxt_catalog",
    label: "PROTACXtend tool catalog",
    description: "List the currently registered PROTACXtend scientific tools (ready only).",
    parameters: Type.Object({}),
    async execute() {
      const b = getBridge(pi);
      const r = await b.call("catalog", {});
      const tools = (r.data as { tools?: { name: string; purpose: string; evidence_type: string }[] })?.tools ?? [];
      const text = tools.map((t) => `- ${t.name} [${t.evidence_type}] ${t.purpose}`).join("\n");
      return { content: [{ type: "text", text: `Registered tools:\n${text}` }], details: { tools } };
    },
  });

  // ── workflow handoff (typed objective → deterministic LangGraph engine) ─
  pi.registerTool({
    name: "pxt_workflow",
    label: "Run PROTACXtend design workflow",
    description:
      "Run the full governed degrader-design workflow from a typed objective " +
      "(target, e3_ligase, objectives, constraints, candidates, cell_line). Use this only " +
      "when the user explicitly asks to design candidates.",
    promptGuidelines: [
      "Use pxt_workflow only for real candidate design/run requests — never for simple factual questions.",
    ],
    parameters: Type.Object({
      target: Type.String(),
      e3_ligase: Type.String(),
      primary_objectives: Type.Optional(Type.Array(Type.String())),
      secondary_objectives: Type.Optional(Type.Array(Type.String())),
      requested_candidates: Type.Optional(Type.Number()),
      cell_line: Type.Optional(Type.String()),
      constraints: Type.Optional(Type.Record(Type.String(), Type.Any())),
    }),
    async execute(_id, params, signal, onUpdate) {
      if (signal?.aborted) return { content: [{ type: "text", text: "cancelled" }], details: {} };
      const b = getBridge(pi);
      onUpdate?.({ content: [{ type: "text", text: "running governed workflow…" }], details: {} });
      const objective = {
        task: "design_protac", target: params.target, e3_ligase: params.e3_ligase,
        primary_objectives: params.primary_objectives ?? ["degradation"],
        secondary_objectives: params.secondary_objectives ?? [],
        requested_candidates: params.requested_candidates ?? null,
        cell_line: params.cell_line ?? null,
        constraints: params.constraints ?? {},
      };
      const r = await b.call("workflow", { objective });
      const summary = (r.data as { summary?: Record<string, unknown> })?.summary ?? {};
      const text = `Workflow complete.\n${truncate(JSON.stringify(summary, null, 2))}`;
      return { content: [{ type: "text", text }], details: { objective, summary } };
    },
  });

  // ── /pxt command: backend/status ─────────────────────────────────────
  pi.registerCommand("pxt", {
    description: "Show PROTACXtend worker/backend status and shared model config",
    async handler(_args, ctx) {
      const b = getBridge(pi);
      const ping = await b.call("ping", {});
      const home = (ping.data as { home?: string })?.home ?? "";
      let model = "unset";
      try {
        const { readFile } = await import("node:fs/promises");
        const config = JSON.parse(await readFile(`${process.env.HOME}/.protacxtend/llm.json`, "utf8"));
        model = `${config.provider} · ${config.model}`;
      } catch { /* not configured yet */ }
      ctx.ui.notify(`PROTACXtend worker ok (home: ${home}) · model: ${model}`, "info");
    },
  });
}
