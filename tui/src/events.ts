/**
 * PROTACXtend Event Renderers v2 — compact scientific event display.
 *
 * Streams Python-backend events with the Laboratory-Night palette:
 * agent phase chips (KNOW/REASON/DESIGN/DISCOVER), evidence rows and
 * one-line tool-result summaries so every skill answers in the CLI.
 */

import { createTheme, type Theme } from "./theme.js";
import { truncateToWidth, padRight, printLine, printError } from "./terminal.js";

const theme = createTheme();

// ── Phase chips ──────────────────────────────────────────────────

export const PHASE_COLORS: Record<string, "violet" | "purple" | "cyan" | "mint"> = {
  KNOW: "violet",
  REASON: "purple",
  DESIGN: "cyan",
  DISCOVER: "mint",
};

export function phaseChip(stage: string): string {
  const key = (stage || "").toUpperCase();
  const color = PHASE_COLORS[key] ?? "violet";
  return theme.fg(color, `[${key}]`);
}

// ── Status indicators ────────────────────────────────────────────

const STATUS_ICONS: Record<string, string> = {
  pending: "○",
  running: "●",
  success: "✓",
  ok: "✓",
  warning: "⚠",
  error: "✗",
  failed: "✗",
};

function statusColor(status: string): "success" | "error" | "muted" {
  return status === "ok" || status === "success" ? "success" : status === "error" ? "error" : "muted";
}

// ── Tool result → one-line summary formatter ─────────────────────

/** Compact single-line summary of a tool result payload (CLI-first). */
export function summarizeToolResult(tool: string, result: unknown): string {
  if (result === null || result === undefined) return String(result ?? "");
  if (typeof result !== "object") return String(result).slice(0, 120);

  const r = result as Record<string, unknown>;
  const parts: string[] = [];

  // Scientific tools with known payload shapes
  if (r.error) return theme.error(`✗ ${String(r.error).slice(0, 110)}`);

  if (tool === "validate_smiles" || tool === "compute_basic_properties") {
    const num = (k: string) => (r[k] !== undefined ? `${k.toUpperCase()} ${r[k]}` : "");
    for (const k of ["mw", "logp", "tpsa", "hbd", "hba", "rotatable_bonds"]) {
      const s = num(k);
      if (s) parts.push(theme.fg("cyan", s));
    }
  } else {
    for (const [k, v] of Object.entries(r)) {
      if (k === "smiles") {
        parts.push(theme.dim(truncateToWidth(`SMILES ${String(v)}`, 46)));
      } else if (k === "routes" && Array.isArray(v)) {
        parts.push(theme.fg("cyan", `routes ${v.length}`));
      } else if (k === "linker_types" && Array.isArray(v)) {
        parts.push(theme.dim(String(v.slice(0, 5).join(" · "))));
      } else if (Array.isArray(v)) {
        parts.push(theme.fg("cyan", `${k} ${v.length}`));
      } else if (typeof v === "object" && v !== null) {
        // nested object → keep it terse
        const first = Object.entries(v as Record<string, unknown>)
          .slice(0, 3)
          .map(([kk, vv]) => `${kk}=${Array.isArray(vv) ? vv.length : truncateToWidth(String(vv), 18)}`)
          .join(" ");
        parts.push(theme.dim(first));
      } else if (v !== undefined && v !== null && v !== "" && k !== "status") {
        parts.push(`${theme.dim(k + " ")}${theme.semantic("text", truncateToWidth(String(v), 26))}`);
      }
    }
  }
  const joined = parts.join("  ").trim();
  return joined || theme.muted("done");
}

// ── Event renderers ──────────────────────────────────────────────

export function renderAgentStart(agentName: string, stage: string): void {
  printLine(`  ${theme.semantic("accent", "◆")} ${theme.semantic("text", agentName)}  ${phaseChip(stage)}`);
}

export function renderAgentComplete(agentName: string, status: string, detail?: string): void {
  const icon = STATUS_ICONS[status] ?? "?";
  const color = statusColor(status);
  printLine(`  ${theme.semantic(color, icon)} ${theme.dim(agentName)}${detail ? "  " + theme.dim(truncateToWidth(detail, 52)) : ""}`);
}

export function renderToolCall(tool: string, args?: Record<string, unknown>): void {
  const argsStr = args
    ? Object.entries(args)
        .filter(([k, v]) => v !== "" && v !== undefined && k !== "smiles")
        .map(([k, v]) => `${k}=${typeof v === "string" ? truncateToWidth(v, 30) : "…"}`)
        .join(" ")
    : "";
  const argLine = argsStr ? ` ${theme.dim(argsStr)}` : "";
  printLine(`    ${theme.muted("⛭")} ${theme.fg("cyan", tool)}${argLine}`);
}

export function renderToolResult(tool: string, status: string, summary?: string): void {
  const icon = STATUS_ICONS[status] ?? "?";
  const color = statusColor(status);
  const body = summary ? `  ${summary}` : "";
  printLine(`    ${theme.semantic(color, icon)} ${theme.dim(tool)}${body}`);
}

export function renderEvidence(source: string, summary: string): void {
  printLine(`    ${theme.semantic("accent", "●")} ${theme.semantic("text", padRight(source, 18))} ${theme.dim(summary)}`);
}

export function renderPrediction(model: string, target: string, value: unknown, confidence: number): void {
  const confStr =
    confidence > 0.7 ? theme.success(`${(confidence * 100).toFixed(0)}%`) :
    confidence > 0.4 ? theme.muted(`${(confidence * 100).toFixed(0)}%`) :
    theme.error(`${(confidence * 100).toFixed(0)}%`);
  printLine(`    ${theme.muted("◈")} ${theme.semantic("text", padRight(model, 16))} ${theme.dim(target)} = ${String(value).slice(0, 20)}  ${confStr}`);
}

export function renderCandidate(candidateId: string, smiles: string, score: number, tier: string): void {
  const scoreStr =
    score > 0.7 ? theme.success(score.toFixed(2)) :
    score > 0.4 ? theme.muted(score.toFixed(2)) :
    theme.error(score.toFixed(2));
  const tierStr = tier ? ` ${theme.fg("cyan", `[${tier}]`)}` : "";
  printLine(`    ${theme.fg("mint", "◆")} ${theme.semantic("text", truncateToWidth(candidateId, 18))} ${scoreStr}${tierStr}`);
  printLine(`      ${theme.dim(truncateToWidth(smiles, 62))}`);
}

export function renderWarning(message: string, source?: string): void {
  const src = source ? ` ${theme.dim(`(${source})`)}` : "";
  printLine(`  ${theme.warning("⚠")} ${theme.dim(truncateToWidth(message, 66))}${src}`);
}

export function renderRunStart(request: string, runId: string): void {
  printLine("");
  printLine(`  ${theme.grad("═══ RUNNING WORKFLOW ═══", "#9B94F0", "#5AB9CD")}`);
  printLine(`  ${theme.dim("request")}  ${theme.semantic("text", truncateToWidth(request, 68))}`);
  printLine(`  ${theme.dim("run_id")}   ${theme.dim(runId)}`);
  printLine("");
}

export function renderRunComplete(status: string, runId: string, summary?: Record<string, unknown>): void {
  const icon = status === "ok" || status === "success" ? "✓" : "✗";
  const color = status === "ok" || status === "success" ? "success" : "error";
  printLine("");
  printLine(`  ${theme.semantic(color, icon)} ${theme.accent("Run complete")} ${theme.dim(`[${runId}]`)}`);
  if (summary) {
    for (const [k, v] of Object.entries(summary)) {
      printLine(`  ${theme.dim(k.padEnd(18))} ${theme.semantic("text", truncateToWidth(String(v), 52))}`);
    }
  }
  printLine("");
}

// ── Catalog renderers ────────────────────────────────────────────

export function renderSkillsList(skills: Record<string, unknown>[]): void {
  printLine("");
  printLine(`  ${theme.grad("═══ SCIENTIFIC SKILLS ═══", "#9B94F0", "#5AB9CD")}  ${theme.dim(`(${skills.length} · /skill <id> for details)`)}`);
  printLine("");
  for (const skill of skills) {
    const id = String(skill.id ?? skill.name ?? "");
    const name = String(skill.name ?? id);
    const api = String(skill.api ?? "");
    const desc = String(skill.desc ?? "");
    const idChip = theme.fg("cyan", padRight(id.slice(0, 26), 26));
    printLine(`  ${idChip} ${theme.semantic("text", name)}${api ? theme.dim(`  · ${api}`) : ""}`);
    if (desc) printLine(`  ${" ".repeat(26)} ${theme.dim(truncateToWidth(desc, 60))}`);
  }
  printLine("");
}

export function renderDatabasesList(databases: Record<string, unknown>[]): void {
  printLine("");
  printLine(`  ${theme.grad("═══ API DATABASES & DATA SOURCES ═══", "#9B94F0", "#5AB9CD")}  ${theme.dim(`(${databases.length})`)}`);
  printLine("");
  for (const db of databases) {
    const name = String(db.name ?? "");
    const url = String(db.url ?? "");
    const auth = String(db.auth ?? "");
    const desc = String(db.desc ?? "");
    const free = !/license|required/i.test(auth);
    const authChip = free ? theme.success("free") : theme.warning("license");
    const line = `  ${theme.semantic("text", padRight(name, 20))} ${theme.dim(truncateToWidth(url, 30))} ${authChip}`;
    printLine(line);
    if (desc) printLine(`  ${" ".repeat(20)} ${theme.dim(truncateToWidth(desc, 58))}`);
  }
  printLine("");
}

// ── Generic event handler ────────────────────────────────────────

export function renderEvent(event: Record<string, unknown>): void {
  const type = event.type as string;
  switch (type) {
    case "agent_start":
      renderAgentStart(event.agent_name as string, event.stage as string);
      break;
    case "agent_complete":
      renderAgentComplete(event.agent_id as string, event.status as string, event.detail as string);
      break;
    case "tool_call":
      renderToolCall(event.tool as string, event.args as Record<string, unknown>);
      break;
    case "tool_result":
      renderToolResult(event.tool as string, event.status as string, summarizeToolResult(event.tool as string, event.result));
      break;
    case "evidence":
      renderEvidence(event.source as string, event.summary as string);
      break;
    case "prediction":
      renderPrediction(event.model as string, event.target as string, event.value, event.confidence as number);
      break;
    case "candidate":
      renderCandidate(event.candidate_id as string, event.smiles as string, event.score as number, event.tier as string);
      break;
    case "warning":
      renderWarning(event.message as string, event.source as string);
      break;
    case "run_start":
      renderRunStart(event.request as string, event.run_id as string);
      break;
    case "run_complete":
      renderRunComplete(event.status as string, event.run_id as string, event.summary as Record<string, unknown>);
      break;
    case "skills_list":
      renderSkillsList(event.skills as Record<string, unknown>[]);
      break;
    case "databases_list":
      renderDatabasesList(event.databases as Record<string, unknown>[]);
      break;
    case "error":
      printError(event.message as string);
      break;
    case "status":
    case "results":
    case "agents":
    case "workflows":
      // handled by the app (needs terminal width / full payload)
      break;
    default:
      break;
  }
}
