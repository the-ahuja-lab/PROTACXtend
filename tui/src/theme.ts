/**
 * PROTACXtend Theme v2 — "Laboratory Night" (PROTACXtend brand palette).
 *
 * Deep-navy terminal surfaces with the PROTACXtend violet → cyan research
 * gradient (inspired by the hero design of the-ahuja-lab.github.io/PROTACXtend
 * and modern neon-glass TUI tooling such as tui.studio).
 *
 * - API-compatible with the earlier Feynman-derived theme (MIT, Companion Inc)
 * - adds per-character gradient text (theme.grad) for signature headers/logo
 *
 * See THIRD_PARTY_NOTICES.md for attribution.
 */

import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ── PROTACXtend "Laboratory Night" palette ───────────────────────
// Brand hues from the project site: violet #8683DD · purple #706BD6 ·
// cyan #5AB9CD · teal #1792A2 — lifted to readable contrast on ink.

const VARS = {
  // surfaces (rarely used directly; bands/fills reference them)
  paper:    "#0C0F22",   // deep space navy
  paper2:   "#141832",
  paper3:   "#1B2144",
  panel:    "#10132A",
  selection: "#262E5C",
  successBg: "#0F2A24",
  errorBg:  "#331B24",

  // text & borders
  ink:      "#E9EAF6",   // near-white periwinkle
  stone:    "#6E77A8",   // subtle border slate
  ash:      "#626A99",   // dim labels
  darkAsh:  "#3A4170",   // muted border

  // semantics
  sage:     "#6FE3BE",   // mint / success (legacy name kept)
  rose:     "#FF7A93",   // coral error
  violet:   "#8E86E8",   // brand violet (accent)
  orange:   "#E9A06C",

  // gradient partners
  purple:   "#706BD6",
  cyan:     "#5AB9CD",
  mint:     "#6FE3BE",
  amber:    "#E8B46B",
  teal:     "#3EC2CF",
} as const;

type ColorName = keyof typeof VARS;

const SEMANTIC = {
  accent:       "violet" as ColorName,
  border:       "stone"  as ColorName,
  borderAccent: "cyan"   as ColorName,
  borderMuted:  "darkAsh" as ColorName,
  success:      "mint"   as ColorName,
  error:        "rose"   as ColorName,
  warning:      "amber"  as ColorName,
  dim:          "ash"    as ColorName,
  text:         "ink"    as ColorName,
  muted:        "stone"  as ColorName,
  protacOrange: "orange" as ColorName,
} as const;

type SemanticName = keyof typeof SEMANTIC;

// ── ANSI escape helpers ──────────────────────────────────────────

const RESET = "\x1b[0m";
const BOLD  = "\x1b[1m";
const DIM   = "\x1b[2m";

function hexRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return [r, g, b];
}

function rgb(hex: string): string {
  const [r, g, b] = hexRgb(hex);
  return `\x1b[38;2;${r};${g};${b}m`;
}

function bgRgb(hex: string): string {
  const [r, g, b] = hexRgb(hex);
  return `\x1b[48;2;${r};${g};${b}m`;
}

/** Linear color interpolation, returns "#rrggbb". */
export function lerpColor(hexA: string, hexB: string, t: number): string {
  const a = hexRgb(hexA);
  const b = hexRgb(hexB);
  const k = Math.max(0, Math.min(1, t));
  const ch = (i: number) => Math.round(a[i] + (b[i] - a[i]) * k);
  const to = (n: number) => n.toString(16).padStart(2, "0");
  return `#${to(ch(0))}${to(ch(1))}${to(ch(2))}`;
}

/** True-color gradient string: from color -> to color over visible chars. */
function gradientString(text: string, c1: string, c2: string, offset: number, span: number): string {
  const len = Math.max(1, span);
  let out = "";
  let idx = 0;
  for (const ch of text) {
    if (ch === " ") {
      out += " "; // spaces need no color
      continue;
    }
    const pos = ((idx + offset) % len) / Math.max(len - 1, 1);
    out += `${rgb(lerpColor(c1, c2, pos))}${ch}${RESET}`;
    idx++;
  }
  return out;
}

// ── Theme object ─────────────────────────────────────────────────

export interface GradOptions {
  /** vertical slant offset (per line) — produces the "angled beam" look */
  offset?: number;
  /** span over which the gradient is stretched (use logo width for coherence) */
  span?: number;
}

export interface Theme {
  /** Get raw ANSI color code for a palette variable */
  raw(name: ColorName): string;
  /** Get raw ANSI color code for a semantic color */
  rawSemantic(name: SemanticName): string;
  /** Colorize text with a palette variable */
  fg(name: ColorName, text: string): string;
  /** Colorize text with a semantic color */
  semantic(name: SemanticName, text: string): string;
  /** Bold text */
  bold(text: string): string;
  /** Dim text */
  dim(text: string): string;
  /** Reset */
  reset: string;
  /** Combined: bold + semantic color */
  accent(text: string): string;
  /** Combined: bold + error color */
  error(text: string): string;
  /** Combined: bold + success color */
  success(text: string): string;
  /** Combined: bold + warning color */
  warning(text: string): string;
  /** Combined: dim */
  muted(text: string): string;
  /** Get hex value for a semantic color */
  hex(name: SemanticName): string;
  /** Resolve a color name or hex string to its hex value */
  hexOf(name: ColorName | string): string;
  /** Per-character violet→cyan gradient text (brand signature). */
  grad(text: string, from?: ColorName | string, to?: ColorName | string, opts?: GradOptions): string;
}

const GRAD_DEFAULT_FROM: ColorName = "violet";
const GRAD_DEFAULT_TO: ColorName = "cyan";

function createTheme(overrides?: Record<string, string>): Theme {
  const vars = { ...VARS, ...overrides };

  const resolveHex = (name: ColorName | string): string =>
    (vars as Record<string, string>)[name] ?? (/^#?[0-9a-fA-F]{6}$/.test(name) ? name.replace("#", "#") : vars.ink);

  return {
    raw: (name) => rgb((vars as Record<string, string>)[name] ?? vars.ink),
    rawSemantic: (name) => rgb((vars as Record<string, string>)[SEMANTIC[name]] ?? vars.ink),
    fg: (name, text) => `${rgb((vars as Record<string, string>)[name] ?? vars.ink)}${text}${RESET}`,
    semantic: (name, text) => `${rgb((vars as Record<string, string>)[SEMANTIC[name]] ?? vars.ink)}${text}${RESET}`,
    bold: (text) => `${BOLD}${text}${RESET}`,
    dim: (text) => `${DIM}${text}${RESET}`,
    reset: RESET,
    accent: (text) => `${BOLD}${rgb((vars as Record<string, string>)[SEMANTIC.accent])}${text}${RESET}`,
    error: (text) => `${BOLD}${rgb((vars as Record<string, string>)[SEMANTIC.error])}${text}${RESET}`,
    success: (text) => `${BOLD}${rgb((vars as Record<string, string>)[SEMANTIC.success])}${text}${RESET}`,
    muted: (text) => `${DIM}${rgb((vars as Record<string, string>)[SEMANTIC.muted])}${text}${RESET}`,
    warning: (text) => `${BOLD}${rgb((vars as Record<string, string>)[SEMANTIC.warning])}${text}${RESET}`,
    hex: (name) => (vars as Record<string, string>)[SEMANTIC[name]] ?? vars.ink,
    hexOf: (name) => resolveHex(name),
    grad: (text, from = GRAD_DEFAULT_FROM, to = GRAD_DEFAULT_TO, opts = {}) =>
      gradientString(text, resolveHex(from), resolveHex(to), opts.offset ?? 0, opts.span ?? text.length),
  };
}

export { createTheme, RESET, BOLD, DIM, rgb, bgRgb };
export type { ColorName, SemanticName };
