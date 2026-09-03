/**
 * PROTACXtend Terminal Rendering — Derived from Feynman src/ui/terminal.ts
 * (MIT, Copyright 2026 Companion, Inc.)
 *
 * Provides box-drawing, panel rendering, and width-aware text utilities.
 * Adapted for PROTACXtend scientific UI.
 */

import { createTheme, RESET, BOLD, DIM, rgb, bgRgb, lerpColor, type Theme } from "./theme.js";

const theme = createTheme();

// ── Visible width (strip ANSI) ───────────────────────────────────

const ANSI_REGEX = /\x1b\[[0-9;]*m/g;

export function visibleWidth(text: string): number {
  return text.replace(ANSI_REGEX, "").length;
}

export function stripAnsi(text: string): string {
  return text.replace(ANSI_REGEX, "");
}

export function truncateToWidth(text: string, max: number, suffix = "…"): string {
  if (visibleWidth(text) <= max) return text;
  const stripped = stripAnsi(text);
  if (stripped.length <= max) return text;
  const cut = max - suffix.length;
  if (cut <= 0) return suffix.slice(0, max);
  // Preserve ANSI codes up to the cut point
  let visible = 0;
  let result = "";
  let inAnsi = false;
  for (const ch of text) {
    if (ch === "\x1b") { inAnsi = true; result += ch; continue; }
    if (inAnsi) { result += ch; if (ch === "m") inAnsi = false; continue; }
    if (visible >= cut) break;
    result += ch;
    visible++;
  }
  return result + suffix;
}

export function padRight(text: string, width: number): string {
  const w = visibleWidth(text);
  if (w >= width) return text;
  return text + " ".repeat(width - w);
}

export function centerText(text: string, width: number): string {
  const w = visibleWidth(text);
  if (w >= width) return text;
  const left = Math.floor((width - w) / 2);
  return " ".repeat(left) + text + " ".repeat(width - w - left);
}

/** Right-align a string to a width (ANSI aware). */
export function padLeft(text: string, width: number): string {
  const w = visibleWidth(text);
  if (w >= width) return text;
  return " ".repeat(width - w) + text;
}

/**
 * True-color horizontal gradient strip (one character row tall).
 * Each cell is a background-colored space, producing a smooth brand band
 * (violet → cyan) ideal for section dividers / card caps.
 */
export function gradientBand(width: number, from = "#8E86E8", to = "#5AB9CD"): string {
  const cells: string[] = [];
  const n = Math.max(1, width);
  for (let i = 0; i < n; i++) {
    const t = n === 1 ? 0 : i / (n - 1);
    cells.push(`${bgRgb(lerpColor(from, to, t))} ${RESET}`);
  }
  return cells.join("");
}

/** Split a terminal row into a left block + right block, padded to a total width. */
export function splitRow(left: string, right: string, width: number, gap = 3): string {
  const lw = Math.max(0, width - visibleWidth(right) - gap);
  return padRight(truncateToWidth(left, lw), lw) + " ".repeat(gap) + truncateToWidth(right, Math.max(0, width - lw - gap));
}

// ── Box drawing ──────────────────────────────────────────────────

export function boxTop(width: number): string {
  return "╭" + "─".repeat(width - 2) + "╮";
}

export function boxBottom(width: number): string {
  return "╰" + "─".repeat(width - 2) + "╯";
}

export function boxSep(width: number): string {
  return "├" + "─".repeat(width - 2) + "┤";
}

export function boxRow(content: string, width: number): string {
  const inner = width - 4; // │ content │
  const padded = padRight(truncateToWidth(content, inner), inner);
  return `│ ${padded} │`;
}

export function boxRowTwoCol(left: string, right: string, width: number, splitRatio = 0.38): string {
  const inner = width - 4;
  const leftW = Math.floor(inner * splitRatio);
  const rightW = inner - leftW - 3; // for " │ "
  const l = padRight(truncateToWidth(left, leftW), leftW);
  const r = padRight(truncateToWidth(right, rightW), rightW);
  return `│ ${l} │ ${r} │`;
}

// ── Printing helpers (Feynman-derived) ───────────────────────────

export function printLine(text: string): void {
  process.stdout.write(text + "\n");
}

export function printInfo(text: string): void {
  printLine(`  ${theme.dim(text)}`);
}

export function printSuccess(text: string): void {
  printLine(`  ${theme.success("✓ " + text)}`);
}

export function printWarning(text: string): void {
  printLine(`  ${theme.muted("⚠ " + text)}`);
}

export function printError(text: string): void {
  printLine(`  ${theme.error("✗ " + text)}`);
}

export function printSection(title: string): void {
  printLine("");
  printLine(`  ${theme.accent("◆ " + title)}`);
}

export function printPanel(title: string, lines: string[] = [], width = 56): void {
  const inner = width - 2;
  printLine("");
  printLine(theme.dim(boxTop(width)));
  printLine(boxRow(theme.accent(title), width));
  if (lines.length > 0) {
    printLine(theme.dim(boxSep(width)));
    for (const line of lines) {
      printLine(boxRow(theme.semantic("text", line), width));
    }
  }
  printLine(theme.dim(boxBottom(width)));
  printLine("");
}

export function printEmptyLine(): void {
  printLine("");
}

/** Print a `label   value` info row with aligned labels (ANSI-aware). */
export function printKv(label: string, value: string, labelWidth = 16): void {
  printLine(`  ${theme.dim(padRight(label, labelWidth))}${value}`);
}

/** Print a bold section header separated by a dim rule. */
export function printRuleHeader(text: string): void {
  printLine("");
  printLine(`  ${theme.accent(text)}`);
  printLine(`  ${theme.dim("─".repeat(56))}`);
}
