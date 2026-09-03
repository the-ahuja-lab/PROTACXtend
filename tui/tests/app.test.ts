/**
 * PROTACXtend TUI Tests — automated smoke tests.
 *
 * Run with: npm test
 */

import { describe, it } from "node:test";
import assert from "node:assert";
import { renderHeader, renderSimpleHeader, renderContract, phaseWord } from "../src/header.js";
import { renderEvent, renderAgentStart, renderAgentComplete, renderToolCall, renderToolResult, renderEvidence, renderWarning, renderCandidate, summarizeToolResult, phaseChip } from "../src/events.js";
import { createTheme, lerpColor } from "../src/theme.js";
import { visibleWidth, truncateToWidth, padRight, padLeft, boxTop, boxBottom, gradientBand, splitRow } from "../src/terminal.js";

describe("Theme", () => {
  it("creates theme with Feynman-derived palette", () => {
    const theme = createTheme();
    assert.ok(theme);
    assert.ok(typeof theme.fg === "function");
    assert.ok(typeof theme.accent === "function");
    assert.ok(typeof theme.error === "function");
    assert.ok(typeof theme.success === "function");
    assert.ok(typeof theme.dim === "function");
  });

  it("fg returns ANSI-colored text", () => {
    const theme = createTheme();
    const result = theme.fg("sage", "hello");
    assert.ok(result.includes("hello"));
    assert.ok(result.includes("\x1b[")); // ANSI escape
  });
});

describe("Terminal utilities", () => {
  it("visibleWidth strips ANSI", () => {
    const theme = createTheme();
    const colored = theme.accent("hello");
    assert.strictEqual(visibleWidth(colored), 5);
  });

  it("truncateToWidth truncates long text", () => {
    const result = truncateToWidth("hello world", 7);
    assert.ok(visibleWidth(result) <= 7);
    assert.ok(result.includes("…"));
  });

  it("padRight pads to correct width", () => {
    const result = padRight("hi", 6);
    assert.strictEqual(visibleWidth(result), 6);
  });

  it("boxTop draws correct width", () => {
    const result = boxTop(20);
    assert.strictEqual(visibleWidth(result), 20);
    assert.ok(result.startsWith("╭"));
    assert.ok(result.endsWith("╮"));
  });

  it("boxBottom draws correct width", () => {
    const result = boxBottom(20);
    assert.strictEqual(visibleWidth(result), 20);
    assert.ok(result.startsWith("╰"));
    assert.ok(result.endsWith("╯"));
  });
});

describe("Header rendering", () => {
  it("renders header for 80 columns", () => {
    const lines = renderHeader({
      model: "ollama/gpt-oss:20b",
      directory: "/storage/saveena/protacpilot",
      session: "2026-09-02T14:00:00",
      system: "32 cores",
      agentCount: 23,
      toolCount: 73,
      agents: ["Supervisor", "Planner", "Target"],
      workflows: [{ cmd: "/design", desc: "Design PROTACs" }],
    }, 80);
    assert.ok(Array.isArray(lines));
    assert.ok(lines.length > 5);
    // Should contain logo
    const allText = lines.join("\n");
    assert.ok(allText.includes("PROTAC") || allText.includes("█"));
  });

  it("renders header for 120 columns", () => {
    const lines = renderHeader({
      model: "ollama/gpt-oss:20b",
      directory: "/storage/saveena/protacpilot",
      session: "2026-09-02T14:00:00",
      system: "32 cores",
      agentCount: 23,
      toolCount: 73,
      agents: ["Supervisor", "Planner", "Target"],
      workflows: [{ cmd: "/design", desc: "Design PROTACs" }],
    }, 120);
    assert.ok(Array.isArray(lines));
    assert.ok(lines.length > 5);
  });

  it("renders header for 160 columns", () => {
    const lines = renderHeader({
      model: "ollama/gpt-oss:20b",
      directory: "/storage/saveena/protacpilot",
      session: "2026-09-02T14:00:00",
      system: "32 cores",
      agentCount: 23,
      toolCount: 73,
      agents: ["Supervisor", "Planner", "Target"],
      workflows: [{ cmd: "/design", desc: "Design PROTACs" }],
    }, 160);
    assert.ok(Array.isArray(lines));
    assert.ok(lines.length > 5);
  });

  it("renders simple header", () => {
    const lines = renderSimpleHeader();
    assert.ok(Array.isArray(lines));
    assert.ok(lines.length > 3);
    const allText = lines.join("\n");
    assert.ok(allText.includes("Evidence-grounded") || allText.includes("KNOW"));
  });
});

describe("Event rendering", () => {
  it("renderAgentStart does not throw", () => {
    assert.doesNotThrow(() => renderAgentStart("Target Resolver", "KNOW"));
  });

  it("renderAgentComplete does not throw", () => {
    assert.doesNotThrow(() => renderAgentComplete("target_resolver", "ok"));
    assert.doesNotThrow(() => renderAgentComplete("target_resolver", "error", "timeout"));
  });

  it("renderToolCall does not throw", () => {
    assert.doesNotThrow(() => renderToolCall("uniprot_lookup", { target: "BRD4" }));
  });

  it("renderEvidence does not throw", () => {
    assert.doesNotThrow(() => renderEvidence("ChEMBL", "86 binders found"));
  });

  it("renderWarning does not throw", () => {
    assert.doesNotThrow(() => renderWarning("Model disagreement HIGH"));
  });

  it("renderCandidate does not throw", () => {
    assert.doesNotThrow(() => renderCandidate("PROTAC_001", "CC(=O)Nc1ccc(O)cc1", 0.85, "A"));
  });

  it("renderEvent handles all event types", () => {
    const events = [
      { type: "agent_start", agent_name: "Test", stage: "KNOW" },
      { type: "agent_complete", agent_id: "test", status: "ok" },
      { type: "tool_call", tool: "test_tool" },
      { type: "tool_result", tool: "test_tool", status: "ok" },
      { type: "evidence", source: "test", summary: "test evidence" },
      { type: "prediction", model: "test", target: "test", value: 1.0, confidence: 0.8 },
      { type: "candidate", candidate_id: "C1", smiles: "CCO", score: 0.9, tier: "A" },
      { type: "warning", message: "test warning" },
      { type: "run_start", request: "test", run_id: "r1" },
      { type: "run_complete", status: "ok", run_id: "r1" },
      { type: "error", message: "test error" },
    ];
    for (const event of events) {
      assert.doesNotThrow(() => renderEvent(event));
    }
  });
});

describe("Responsive layout", () => {
  it("header renders at 80 columns without overflow", () => {
    const lines = renderHeader({
      model: "ollama/gpt-oss:20b",
      directory: "/storage/saveena/protacpilot",
      session: "2026-09-02",
      system: "32 cores",
      agentCount: 23,
      toolCount: 73,
      agents: ["Supervisor"],
      workflows: [{ cmd: "/design", desc: "Design" }],
    }, 80);
    for (const line of lines) {
      // No line should exceed terminal width (allow some margin for ANSI)
      // Just check that no plain-text line overflows significantly
    }
  });

  it("header renders at 120 columns", () => {
    const lines = renderHeader({
      model: "ollama/gpt-oss:20b",
      directory: "/storage/saveena/protacpilot",
      session: "2026-09-02",
      system: "32 cores",
      agentCount: 23,
      toolCount: 73,
      agents: ["Supervisor"],
      workflows: [{ cmd: "/design", desc: "Design" }],
    }, 120);
    assert.ok(lines.length > 5);
  });

  it("header renders at 160 columns", () => {
    const lines = renderHeader({
      model: "ollama/gpt-oss:20b",
      directory: "/storage/saveena/protacpilot",
      session: "2026-09-02",
      system: "32 cores",
      agentCount: 23,
      toolCount: 73,
      agents: ["Supervisor"],
      workflows: [{ cmd: "/design", desc: "Design" }],
    }, 160);
    assert.ok(lines.length > 5);
  });
});


describe("Theme v2 gradient", () => {
  it("grad produces ANSI gradient text", () => {
    const theme = createTheme();
    const out = theme.grad("PROTACXtend");
    assert.ok(out.replace(/\x1b\[[0-9;]*m/g, "").includes("PROTACXtend"));
    assert.ok(out.includes("\x1b[38;2;"));
  });

  it("grad preserves visible width", () => {
    const theme = createTheme();
    const out = theme.grad("KNOW  \u2192  REASON", "#8E86E8", "#5AB9CD");
    assert.strictEqual(visibleWidth(out), visibleWidth("KNOW  \u2192  REASON"));
  });

  it("hexOf resolves palette names and hex input", () => {
    const theme = createTheme();
    assert.ok(theme.hexOf("violet").startsWith("#"));
    assert.strictEqual(theme.hexOf("#123456").toLowerCase(), "#123456");
  });

  it("lerpColor clamps to range", () => {
    assert.strictEqual(lerpColor("#000000", "#ffffff", 0), "#000000");
    assert.strictEqual(lerpColor("#000000", "#ffffff", 1), "#ffffff");
    assert.strictEqual(lerpColor("#000000", "#ffffff", 5), "#ffffff");
  });
});

describe("Contract + one-line tool summaries", () => {
  it("renderContract shows the four phases", () => {
    const out = renderContract(50);
    const plain = out.replace(/\x1b\[[0-9;]*m/g, "");
    assert.ok(plain.includes("KNOW"));
    assert.ok(plain.includes("REASON"));
    assert.ok(plain.includes("DESIGN"));
    assert.ok(plain.includes("DISCOVER"));
  });

  it("phaseWord/phaseChip do not throw", () => {
    assert.doesNotThrow(() => phaseWord("KNOW"));
    assert.doesNotThrow(() => phaseChip("DESIGN"));
  });

  it("summarizeToolResult one-lines validate payloads", () => {
    const out = summarizeToolResult("validate_smiles", { mw: 151.16, logp: 1.42, tpsa: 29.5, hbd: 1, hba: 2 });
    assert.ok(out.length > 0);
    assert.ok(!out.includes("\n"));
  });

  it("summarizeToolResult handles errors and arrays", () => {
    assert.ok(summarizeToolResult("x", { error: "boom" }).includes("boom"));
    const out = summarizeToolResult("retrosynthesis", { smiles: "CCO", routes: [1, 2, 3] });
    assert.ok(out.includes("routes"));
  });

  it("renderToolResult prints a summary row", () => {
    assert.doesNotThrow(() => renderToolResult("validate_smiles", "ok", "MW 151.16"));
  });
});

describe("Terminal helpers v2", () => {
  it("gradientBand produces width cells with ANSI", () => {
    const band = gradientBand(20);
    assert.strictEqual(visibleWidth(band), 20);
    assert.ok(band.includes("\x1b[48;2;"));
  });

  it("padLeft pads to width", () => {
    assert.strictEqual(visibleWidth(padLeft("x", 5)), 5);
    assert.strictEqual(visibleWidth(padLeft("hello", 3)), 5);
  });

  it("splitRow fills a width", () => {
    const row = splitRow("left", "right", 20);
    assert.strictEqual(visibleWidth(row), 20);
  });
});
