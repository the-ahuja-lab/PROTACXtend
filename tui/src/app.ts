/**
 * PROTACXtend TUI Application v2 — "Laboratory Night" command center.
 *
 * Launches the Python backend, renders the branded dashboard header,
 * handles input, and streams workflow events with CLI-first one-line
 * result summaries for every skill.
 *
 * No runtime dependencies: pure Node + true-color ANSI.
 */

import * as readline from "node:readline";
import { cpus, totalmem } from "node:os";
import { PythonBridge, type BridgeEvent } from "./bridge.js";
import { renderHeader, renderSimpleHeader, renderContract, type HeaderData } from "./header.js";
import { renderEvent } from "./events.js";
import { createTheme } from "./theme.js";
import {
  printLine,
  printInfo,
  printSuccess,
  printWarning,
  printError,
  printSection,
  printPanel,
  printKv,
  printRuleHeader,
  visibleWidth,
  truncateToWidth,
  padRight,
  centerText,
} from "./terminal.js";

const theme = createTheme();

// ── Version & identity ───────────────────────────────────────────

const VERSION = "0.3.0";
const REPO_URL = "https://github.com/the-ahuja-lab/PROTACXtend";
const SITE_URL = "https://the-ahuja-lab.github.io/PROTACXtend";
const LAUNCH_URL = "https://raw.githubusercontent.com/the-ahuja-lab/PROTACXtend/main/tui/launch.sh";

/** Skill id → recommended CLI route (ids follow protacxtend/tui_bridge/events.py). */
const SKILL_GUIDE: Record<string, { cmd: string; example: string }> = {
  target_resolution: { cmd: "/design", example: "/design BRD4 PROTAC design" },
  binder_search: { cmd: "/evidence", example: "/evidence BRD4 binders" },
  warhead_selection: { cmd: "/design", example: "/design CRBN PROTACs for BRD4" },
  e3_ligand_selection: { cmd: "/design", example: "/design VHL PROTAC for EGFR" },
  exit_vector: { cmd: "/design", example: "/design a cereblon PROTAC for BRD4" },
  linker_generation: { cmd: "/generator", example: "/generator PEG linkers for BRD4 PROTAC" },
  molecular_construction: { cmd: "/design", example: "/design build PROTAC from pomalidomide" },
  stereochemistry: { cmd: "/stereo", example: "/stereo CC(=O)Nc1ccc(O)cc1" },
  degradation_prediction: { cmd: "/design", example: "/design predict DC50 for BRD4 PROTAC" },
  admet_prediction: { cmd: "/validate", example: "/validate CC(=O)Nc1ccc(O)cc1" },
  ternary_feasibility: { cmd: "/design", example: "/design ternary feasibility BRD4 CRBN" },
  docking: { cmd: "/docking", example: "/docking CC(=O)Nc1ccc(O)cc1 [target.pdb]" },
  retrosynthesis: { cmd: "/retro", example: "/retro CC(=O)Nc1ccc(O)cc1" },
  novelty_check: { cmd: "/design", example: "/design novelty-scored PROTAC BRD4" },
  ranker: { cmd: "/design", example: "/design rank top BRD4 degraders" },
  diversity: { cmd: "/design", example: "/design diverse PROTACs for BRD4" },
  reporting: { cmd: "/report", example: "/design BRD4 PROTACs (report auto-emitted)" },
  memory: { cmd: "/learn", example: "/design then /learn to feed back" },
  linker_scanner: { cmd: "/generator", example: "/generator scan linkers x attachment points" },
  hook_effect: { cmd: "/design", example: "/design hook-effect aware dosing" },
  cooperativity: { cmd: "/structure", example: "/structure BRD4 CRBN cooperativity" },
  proteome_selectivity: { cmd: "/design", example: "/design cell-context aware BRD4" },
  p4ward: { cmd: "/design", example: "/design full P4ward ternary simulation" },
};

// ── Help catalogue ───────────────────────────────────────────────

const COMMAND_GROUPS: { title: string; rows: [string, string][] }[] = [
  {
    title: "DESIGN & DISCOVER",
    rows: [
      ["/design <objective>", "Full evidence → candidate → ranking run"],
      ["/run <objective>", "Alias of /design (execute workflow)"],
      ["/evidence <target>", "Retrieval pass (PROTAC-DB, literature)"],
      ["/structure <q>", "Ternary feasibility, cooperativity, lysine reach"],
      ["/cellctx <q>", "Score target/E3 abundance per cell line"],
      ["/rank <q>", "Multi-objective ranking with uncertainty"],
      ["/plan", "Fast plan-only estimate (no execution)"],
      ["/learn <q>", "Active-learning feedback loop"],
    ],
  },
  {
    title: "MOLECULAR TOOLS",
    rows: [
      ["/validate <SMILES>", "RDKit validation + ADMET proxies, one line"],
      ["/retro <SMILES>", "Retrosynthesis (ASKCOS + AiZynthFinder)"],
      ["/docking <SMILES> [pdb]", "AutoDock Vina docking"],
      ["/stereo <SMILES>", "Stereochemistry + isomer enumeration"],
      ["/generator <request>", "Linker engine (PEG, alkyl, rigid, triazole…)"],
    ],
  },
  {
    title: "SCIENCE CATALOG",
    rows: [
      ["/skills", "List every scientific skill"],
      ["/skill <id|partial>", "Skill profile + how to run it"],
      ["/databases", "API databases & data sources"],
    ],
  },
  {
    title: "SYSTEM & HELP",
    rows: [
      ["/status", "System · model · dependencies health"],
      ["/agents", "23-node agent pipeline view"],
      ["/workflows", "Full workflow catalogue"],
      ["/contract", "KNOW → REASON → DESIGN → DISCOVER"],
      ["/about", "Project, architecture, validation, launch"],
      ["/launch", "One-line curl launch recipes"],
      ["/help", "This command reference"],
      ["/clear", "Clear screen + redraw header"],
      ["/quit", "Exit PROTACXtend"],
    ],
  },
];

// ── Main App ─────────────────────────────────────────────────────

export class ProtacXtendApp {
  private bridge: PythonBridge;
  private rl: readline.Interface | null = null;
  private running = false;
  private prompt = "PROTACXtend> ";
  private agentCount = 23;
  private toolCount = 73;
  private skillsCount = 0;
  private databaseCount = 0;
  private agents: string[] = [];
  private workflows: { cmd: string; desc: string }[] = [];
  private lastActivity = "";
  private skillsCache: Record<string, unknown>[] | null = null;

  constructor() {
    this.bridge = new PythonBridge();
    this.setupBridgeHandlers();
  }

  private setupBridgeHandlers(): void {
    this.bridge.on("event", (event: BridgeEvent) => {
      renderEvent(event as Record<string, unknown>);
      this.onBridgeEvent(event);
    });

    this.bridge.on("stderr", (msg: string) => {
      if (msg.includes("Error") || msg.includes("Traceback")) {
        printWarning(`backend: ${truncateToWidth(msg, 58)}`);
      }
    });

    this.bridge.on("error", (err: Error) => {
      printError(`Bridge error: ${err.message}`);
    });

    this.bridge.on("exit", (code: number | null) => {
      if (code !== 0 && code !== null) {
        printWarning(`Python backend exited with code ${code}`);
      }
    });
  }

  /** Route non-rendered events to app-level panels. */
  private onBridgeEvent(event: BridgeEvent): void {
    switch (event.type) {
      case "status":
        // fields consumed by priming / /status (rendered on demand)
        break;
      case "agents": {
        const list = (event.agents as Array<Record<string, unknown>>) || [];
        this.agents = list.map((a) => String(a.name ?? a.id ?? "")).filter(Boolean);
        if (list.length) this.agentCount = list.length;
        break;
      }
      case "workflows": {
        const list = (event.workflows as Array<{ cmd: string; desc: string }>) || [];
        if (list.length) this.workflows = list;
        break;
      }
      case "results":
        this.showResults(event as Record<string, unknown>);
        break;
      case "skills_list":
        this.skillsCache = (event.skills as Record<string, unknown>[]) || [];
        this.skillsCount = this.skillsCache.length;
        break;
      case "databases_list":
        this.databaseCount = ((event.databases as Record<string, unknown>[]) || []).length;
        break;
      default:
        break;
    }
  }

  /** Ask backend for a payload and resolve when the matching event arrives. */
  private ask(type: string, want: string[], timeoutMs = 10_000): Promise<Record<string, unknown> | undefined> {
    return new Promise((resolve) => {
      let settled = false;
      const onEvent = (event: BridgeEvent) => {
        if (event.type === want.find((w) => w === event.type)) {
          cleanup();
          resolve(event as Record<string, unknown>);
        }
      };
      const cleanup = () => {
        clearTimeout(timer);
        this.bridge.removeListener("event", onEvent);
      };
      const timer = setTimeout(() => {
        if (!settled) {
          settled = true;
          cleanup();
          resolve(undefined);
        }
      }, timeoutMs);
      this.bridge.on("event", onEvent);
      try {
        this.bridge.send(type);
      } catch {
        cleanup();
        resolve(undefined);
      }
    });
  }

  async start(): Promise<void> {
    printInfo("Starting PROTACXtend backend…");
    try {
      await this.bridge.start();
    } catch (err) {
      printError(`Failed to start backend: ${err instanceof Error ? err.message : err}`);
      printInfo("Falling back to simple mode.");
      this.runSimpleMode();
      return;
    }

    // Prime the header with real backend data (no panels — drawn after header)
    const status = await this.ask("status", ["status"], 12_000);
    if (status) {
      const llm = (status.llm as Record<string, unknown>) || {};
      this.agentCount = Number(status.agents ?? this.agentCount);
      this.skillsCount = Number(status.skills ?? 0);
      this.databaseCount = Number(status.databases ?? 0);
      void llm;
    }
    await this.ask("agents", ["agents"]);
    await this.ask("workflows", ["workflows"]);

    await this.printHeader();
    this.runInteractive();
  }

  private async printHeader(): Promise<void> {
    const termWidth = process.stdout.columns ?? 80;
    const session = new Date().toISOString().slice(0, 19).replace("T", " · ");
    const mem = Math.round((totalmem() / 1024 ** 3));
    const data: HeaderData = {
      model: process.env.PROTACXTEND_MODEL || "ollama/gpt-oss:20b (auto)",
      directory: process.cwd(),
      session,
      system: `${cpus().length} cores · ${mem} GB RAM${process.env.PROTACXTEND_GPU ? ` · ${process.env.PROTACXTEND_GPU}` : ""}`,
      agentCount: this.agentCount,
      toolCount: this.toolCount,
      skillsCount: this.skillsCount || undefined,
      agents: this.agents.length > 0 ? this.agents : [
        "Supervisor", "Planner", "Target Resolver", "Binder Retrieval",
        "Warhead Selection", "E3 Ligand", "Linker", "Construction",
        "Ranking", "Report",
      ],
      workflows: this.workflows.length > 0 ? this.workflows : [
        { cmd: "/design", desc: "Design and rank PROTAC candidates" },
        { cmd: "/evidence", desc: "Retrieve literature + affinity data" },
        { cmd: "/validate", desc: "RDKit validation + ADMET proxies" },
        { cmd: "/retro", desc: "Retrosynthesis route planning" },
        { cmd: "/docking", desc: "AutoDock Vina docking" },
        { cmd: "/stereo", desc: "Stereochemistry analysis" },
        { cmd: "/generator", desc: "Linker engine" },
        { cmd: "/skills", desc: "List scientific skills" },
        { cmd: "/status", desc: "System status" },
        { cmd: "/help", desc: "Show commands" },
      ],
      lastActivity: this.lastActivity || undefined,
    };

    const lines = renderHeader(data, termWidth);
    for (const line of lines) {
      printLine(line);
    }
  }

  // ── REPL ───────────────────────────────────────────────────────

  private commandHints(): string[] {
    const list = new Set<string>();
    for (const g of COMMAND_GROUPS) for (const [cmd] of g.rows) list.add(cmd);
    for (const k of Object.keys(SKILL_GUIDE)) list.add(`/skill ${k}`);
    list.add("/retrosynthesis");
    return [...list];
  }

  private runInteractive(): void {
    const hints = this.commandHints();
    this.rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      prompt: this.prompt,
      completer: (line: string) => {
        const hits = hints.filter((c) => c.startsWith(line.trim()));
        return [hits.length ? hits : hints.slice(0, 8), line];
      },
    });

    this.running = true;
    this.rl.prompt();

    this.rl.on("line", async (input: string) => {
      const trimmed = input.trim();
      if (!trimmed) {
        this.rl?.prompt();
        return;
      }
      await this.handleInput(trimmed);
      if (this.running) this.rl?.prompt();
    });

    this.rl.on("close", () => {
      this.running = false;
      this.bridge.stop();
    });

    process.on("SIGINT", () => {
      printLine("");
      printInfo("Use /quit to exit.");
      this.rl?.prompt();
    });
  }

  private async handleInput(input: string): Promise<void> {
    if (input.startsWith("/")) {
      await this.handleCommand(input);
    } else {
      await this.handleDesignRequest(input);
    }
  }

  // ── Commands ───────────────────────────────────────────────────

  private async handleCommand(input: string): Promise<void> {
    const parts = input.split(/\s+/);
    let cmd = parts[0].toLowerCase();
    const args = parts.slice(1).join(" ").trim();

    // aliases
    if (cmd === "/retrosynthesis") cmd = "/retro";

    switch (cmd) {
      case "/help":
        this.showHelp();
        break;
      case "/about":
        this.showAbout();
        break;
      case "/launch":
        this.showLaunch();
        break;
      case "/status":
      case "/models": {
        printInfo("Requesting system status…");
        const ev = await this.ask("status", ["status"]);
        if (ev) this.renderStatusPanel(ev);
        else printWarning("No status payload received from backend.");
        break;
      }
      case "/agents": {
        printInfo("Requesting agent pipeline…");
        const ev = await this.ask("agents", ["agents"]);
        if (ev) this.renderAgentsPanel(ev);
        else printWarning("No agents payload received.");
        break;
      }
      case "/workflows": {
        printInfo("Requesting workflow catalogue…");
        const ev = await this.ask("workflows", ["workflows"]);
        if (ev) this.renderWorkflowsPanel(ev);
        else printWarning("No workflows payload received.");
        break;
      }
      case "/skills": {
        printInfo("Opening the skill catalogue…");
        const ev = await this.ask("skills", ["skills_list"]);
        if (!ev) printWarning("Skill catalogue not received from backend.");
        break;
      }
      case "/databases": {
        printInfo("Opening data sources…");
        const ev = await this.ask("databases", ["databases_list"]);
        if (!ev) printWarning("Database list not received from backend.");
        break;
      }
      case "/skill": {
        const tokens = input.split(/\s+/).slice(1);
        const id = tokens[0] ?? "";
        const skillArgs = tokens.slice(1).join(" ");
        await this.runSkill(id, skillArgs);
        break;
      }

      // ── design / run ──
      case "/design":
      case "/run":
        if (args) await this.handleDesignRequest(args);
        else this.showUsage(cmd, "a design objective", "BRD4 degraders via CRBN");
        break;
      case "/evidence":
        if (args) await this.handleDesignRequest(`Evidence search: ${args}`);
        else this.showUsage(cmd, "a target/question", "BRD4 degradation evidence");
        break;
      case "/cellctx":
        if (args) await this.handleDesignRequest(`Cell-context scoring: ${args}`);
        else this.showUsage(cmd, "a target/E3 pair", "BRD4 CRBN in MDA-MB-231");
        break;
      case "/structure":
        this.showStructure(args);
        break;
      case "/rank":
        if (args) await this.handleDesignRequest(`Rank candidates: ${args}`);
        else this.showUsage(cmd, "a ranking objective", "rank top BRD4 PROTACs by DC50 + ADMET");
        break;
      case "/learn":
        this.showLearn(args);
        break;
      case "/report":
        if (args) await this.handleDesignRequest(`Generate report: ${args}`);
        else this.showUsage(cmd, "a completed design", "report on the BRD4 run");
        break;
      case "/contract":
        this.showContract();
        break;
      case "/plan":
        this.showPlan();
        break;

      // ── molecular tools ──
      case "/validate":
        if (args) this.bridge.send("validate", { smiles: args });
        else this.showUsage(cmd, "<SMILES>", "/validate CC(=O)Nc1ccc(O)cc1");
        break;
      case "/retro":
        if (args) this.bridge.send("retrosynthesis", { smiles: args });
        else this.showUsage(cmd, "<SMILES>", "/retro CC(=O)Nc1ccc(O)cc1");
        break;
      case "/docking":
        if (args) {
          const [smiles, target] = args.split(/\s+/);
          this.bridge.send("docking", { smiles, target: target || "" });
        } else {
          this.showUsage(cmd, "<SMILES> [target.pdb]", "/docking CC(=O)Nc1ccc(O)cc1 7q1c.pdb");
        }
        break;
      case "/stereo":
        if (args) this.bridge.send("stereo", { smiles: args });
        else this.showUsage(cmd, "<SMILES>", "/stereo CC(=O)Nc1ccc(O)cc1");
        break;
      case "/generator":
        if (args) this.bridge.send("generator", { request: args });
        else this.showUsage(cmd, "<request>", "/generator rigid triazole linkers");
        break;

      case "/clear":
        process.stdout.write("\x1b[2J\x1b[H");
        await this.printHeader();
        break;
      case "/quit":
      case "/exit":
        this.running = false;
        this.bridge.stop();
        printSuccess("Goodbye — evidence over everything.");
        process.exit(0);
        break;
      default:
        printWarning(`Unknown command: ${cmd}`);
        printInfo("Type /help for the command centre.");
    }
  }

  private showUsage(cmd: string, what: string, example: string): void {
    printInfo(`Usage: ${cmd} ${what}`);
    printLine(`  ${theme.dim("example")}  ${theme.semantic("text", example)}`);
  }

  // ── Skill execution ────────────────────────────────────────────────

  /** `/skill <id>` shows the profile · `/skill <id> <args>` also runs it. */
  private async runSkill(query: string, skillArgs: string): Promise<void> {
    if (!query) {
      printInfo("Usage: /skill <id|partial> [args]");
      printInfo("       e.g.  /skill stereochemistry CC(=O)Nc1ccc(O)cc1   (profile + run)");
      printInfo("             /skill linker_generation                    (profile only)");
      printInfo("See /skills for the full catalogue.");
      return;
    }
    let skills = this.skillsCache;
    if (!skills) {
      const ev = await this.ask("skills", ["skills_list"]);
      skills = (ev?.skills as Record<string, unknown>[]) || null;
      if (!skills) {
        printWarning("Skill catalogue not available (backend offline).");
        return;
      }
    }
    const q = query.toLowerCase();
    const hit =
      skills.find((s) => String(s.id ?? "").toLowerCase() === q || String(s.name ?? "").toLowerCase() === q) ||
      skills.find((s) => String(s.id ?? "").toLowerCase().includes(q) || String(s.name ?? "").toLowerCase().includes(q));
    if (!hit) {
      printWarning(`No skill matches "${query}". Try /skills.`);
      return;
    }
    const id = String(hit.id ?? "");
    const guide = SKILL_GUIDE[id];
    const rows: string[] = [
      `${theme.dim("name".padEnd(12))} ${theme.semantic("text", String(hit.name ?? id))}`,
      `${theme.dim("api".padEnd(12))} ${theme.fg("cyan", String(hit.api ?? ""))}`,
      "",
      `  ${theme.dim(String(hit.desc ?? ""))}`,
    ];
    if (guide) {
      rows.push("", `${theme.dim("run via".padEnd(12))} ${theme.fg("mint", guide.cmd)} ${theme.dim(`— ${guide.example}`)}`);
    } else {
      rows.push("", `${theme.dim("run via".padEnd(12))} ${theme.fg("mint", "/design <objective>")}  ${theme.dim("(routed through the agent graph)")}`);
    }
    printPanel(`SKILL PROFILE · ${id}`, rows, 74);

    // Execute the skill when arguments were provided
    if (skillArgs && guide) {
      printInfo(`Running skill ${id} with: ${skillArgs}`);
      await this.executeGuided(guide.cmd, skillArgs);
    } else if (skillArgs && !guide) {
      printInfo(`No direct CLI route for ${id} — running through the agent graph…`);
      await this.handleDesignRequest(`${id}: ${skillArgs}`);
    }
  }

  /** Translate a skill's recommended command into an actual execution. */
  private async executeGuided(cmd: string, argsText: string): Promise<void> {
    switch (cmd) {
      case "/validate":
      case "/retro":
      case "/stereo":
        if (!argsText) break;
        this.bridge.send(cmd === "/retro" ? "retrosynthesis" : cmd === "/stereo" ? "stereo" : "validate", { smiles: argsText });
        break;
      case "/docking": {
        const [smiles, target] = argsText.split(/\s+/);
        if (!smiles) break;
        this.bridge.send("docking", { smiles, target: target || "" });
        break;
      }
      case "/generator":
        if (!argsText) break;
        this.bridge.send("generator", { request: argsText });
        break;
      case "/evidence":
        await this.handleDesignRequest(`Evidence search: ${argsText}`);
        break;
      case "/structure":
        printInfo(`Structure analysis: ${argsText}`);
        printInfo("Run /design with the same objective for the full feasibility pass.");
        break;
      case "/learn":
        printSection("ACTIVE LEARNING");
        printLine(`  ${theme.dim("feedback")}  ${theme.semantic("text", argsText || "improve next run")}`);
        break;
      case "/design":
      case "/run":
      default:
        await this.handleDesignRequest(argsText || "general design objective");
    }
  }

  // ── Design request execution ───────────────────────────────────

  private async handleDesignRequest(request: string): Promise<void> {
    printLine("");
    this.bridge.send("run", { request });
    await new Promise<void>((resolve) => {
      const handler = (event: BridgeEvent) => {
        if (event.type === "run_complete") {
          this.bridge.removeListener("event", handler);
          resolve();
        }
      };
      this.bridge.on("event", handler);
    });
  }

  // ── Results rendering (one-line-first) ─────────────────────────

  private showResults(event: Record<string, unknown>): void {
    printLine("");
    printLine(`  ${theme.grad("─".repeat(58), "#9B94F0", "#5AB9CD")}`);
    printLine(`  ${theme.accent("WORKFLOW RESULT")}  ${theme.dim("· one-line summary · full reports in outputs/")}`);

    const metric = (label: string, value: unknown) =>
      Number(value) > 0 ? `${theme.dim(label + " ")}${theme.fg("mint", String(value))}` : null;

    const metrics = [
      metric("candidates", event.candidates_generated),
      metric("ranked", event.candidates_ranked),
      metric("binders", event.binders_found),
      metric("warheads", event.warheads_selected),
      metric("E3", event.e3_ligands_selected),
      metric("linkers", event.linkers_generated),
    ].filter(Boolean) as string[];

    printLine(`  ${metrics.length ? metrics.join(theme.dim("  ·  ")) : theme.muted("pipeline produced no countable outputs for this objective")}`);
    printLine(`  ${theme.grad("─".repeat(58), "#9B94F0", "#5AB9CD")}`);

    const candidates = event.top_candidates as Array<Record<string, unknown>> | undefined;
    if (candidates && candidates.length > 0) {
      printLine("");
      printSection("TOP CANDIDATES");
      for (let i = 0; i < Math.min(candidates.length, 5); i++) {
        const c = candidates[i];
        const score = typeof c.score === "number" ? c.score.toFixed(3) : String(c.score ?? "?");
        const tier = c.tier ? ` ${theme.fg("cyan", `[${c.tier}]`)}` : "";
        const scoreColored = typeof c.score === "number"
          ? (c.score > 0.7 ? theme.success(score) : c.score > 0.4 ? theme.muted(score) : theme.error(score))
          : theme.semantic("text", score);
        const comps = [c.warhead ? `war ${c.warhead}` : "", c.e3 ? `e3 ${c.e3}` : "", c.linker ? `linker ${c.linker}` : ""]
          .filter(Boolean).join(" · ");
        const head = `${theme.accent(`#${i + 1}`)}  ${theme.semantic("text", String(c.candidate_id ?? "?"))}  ${scoreColored}${tier}`;
        printLine(`  ${head}`);
        if (c.smiles) printLine(`      ${theme.dim(truncateToWidth(String(c.smiles), 72))}`);
        if (comps) printLine(`      ${theme.dim(comps)}`);
      }
    }

    if (event.report_preview) {
      printLine("");
      printSection("REPORT PREVIEW");
      const preview = String(event.report_preview);
      for (const line of preview.split("\n").slice(0, 6)) {
        if (line.trim()) printLine(`  ${theme.dim(truncateToWidth(line, 74))}`);
      }
    }
    printLine("");
    printLine(`  ${theme.dim("→ results saved under")} ${theme.fg("mint", "outputs/")} ${theme.dim("— rerun anytime with /design")}`);
    printLine("");
  }

  // ── Panels ─────────────────────────────────────────────────────

  private renderStatusPanel(ev: Record<string, unknown>): void {
    const llm = (ev.llm as Record<string, unknown>) || {};
    const deps = (ev.dependencies as Record<string, unknown>) || {};
    printLine("");
    printLine(`  ${theme.grad("═══ SYSTEM STATUS ═══", "#9B94F0", "#5AB9CD")}`);
    printRuleHeader("RUNTIME");
    printKv("project root", theme.dim(String(ev.project_root ?? "")), 16);
    printKv("software", theme.fg("mint", `v${ev.version ?? VERSION}`), 16);
    printKv("llm", `${theme.semantic("text", `${String(llm.provider ?? "—")}/${String(llm.model ?? "—")}`)}  ${llm.healthy ? theme.success("healthy") : theme.error("unhealthy")}`, 16);
    printKv("node graph", `${theme.fg("mint", String(ev.agents ?? this.agentCount))} agents · ${theme.fg("mint", String(ev.workflows ?? "—"))} workflows · ${theme.fg("mint", String(ev.skills ?? this.skillsCount))} skills · ${theme.fg("mint", String(ev.databases ?? this.databaseCount))} databases`, 16);

    const depNames = Object.keys(deps);
    if (depNames.length) {
      printRuleHeader("DEPENDENCIES");
      const chips = depNames.map((d) => {
        const v = String(deps[d]);
        return v === "missing" ? `${theme.dim(d)} ${theme.error("✗")}` : `${theme.semantic("text", d)} ${theme.dim(v)}`;
      });
      let line = "  ";
      for (const chip of chips) {
        const w = visibleWidth(chip);
        if (visibleWidth(line) + w + 4 > 74) {
          printLine(line);
          line = "  ";
        }
        line += chip + theme.dim("  ·  ");
      }
      if (line.trim()) printLine(line.replace(/  ·\s*$/, ""));
    }
    printLine("");
    printSuccess("status refreshed");
    printLine("");
  }

  private renderAgentsPanel(ev: Record<string, unknown>): void {
    const agents = (ev.agents as Array<Record<string, unknown>>) || [];
    printLine("");
    printLine(`  ${theme.grad("═══ AGENT PIPELINE ═══", "#9B94F0", "#5AB9CD")}  ${theme.dim(`(${agents.length} nodes)`)}`);
    printLine("");
    const rows: string[] = [];
    for (const a of agents) {
      const stage = String(a.stage ?? "KNOW");
      const stageChip = theme.fg(
        stage === "KNOW" ? "violet" : stage === "REASON" ? "purple" : stage === "DESIGN" ? "cyan" : "mint",
        `[${stage}]`,
      );
      const id = String(a.id ?? "");
      const name = String(a.name ?? id);
      rows.push(`  ${stageChip}  ${theme.semantic("text", padRight(name, 30))} ${theme.dim(id)}`);
    }
    // two-column when terminal wide
    const width = process.stdout.columns ?? 80;
    if (width >= 96) {
      const col = Math.ceil(rows.length / 2);
      const cols: [string, string][] = [];
      for (let i = 0; i < col; i++) {
        const left = rows[i] ?? "";
        const right = rows[i + col] ?? "";
        cols.push([left, right]);
      }
      for (const [l, r] of cols) {
        printLine(`${l}${r ? " " + r : ""}`);
      }
    } else {
      for (const row of rows) printLine(row);
    }
    printLine("");
    printLine(`  ${theme.dim("KNOW")}  retrieval & verification   ${theme.dim("REASON")}  warhead/E3/exit-vector choice`);
    printLine(`  ${theme.dim("DESIGN")}  build, validate, predict    ${theme.dim("DISCOVER")}  rank, diversify, reflect, report`);
    printLine("");
  }

  private renderWorkflowsPanel(ev: Record<string, unknown>): void {
    const wfs = (ev.workflows as Array<{ cmd: string; desc: string }>) || [];
    printLine("");
    printLine(`  ${theme.grad("═══ WORKFLOWS ═══", "#9B94F0", "#5AB9CD")}  ${theme.dim(`(${wfs.length})`)}`);
    printLine("");
    const width = process.stdout.columns ?? 80;
    const descW = width >= 100 ? 60 : 44;
    for (const wf of wfs) {
      const cmd = theme.fg("mint", padRight(wf.cmd, 18));
      printLine(`  ${cmd} ${theme.dim(truncateToWidth(wf.desc, descW))}`);
    }
    printLine("");
  }

  // ── Help ───────────────────────────────────────────────────────

  private showHelp(): void {
    const width = Math.min(process.stdout.columns ?? 100, 110);
    const lineW = width - 6;
    printLine("");
    printLine(`  ${theme.grad("PROTACXtend — COMMAND CENTRE", "#9B94F0", "#5AB9CD")}`);
    printLine(`  ${theme.dim("─".repeat(Math.min(lineW, 74)))}`);
    printLine("");

    for (const group of COMMAND_GROUPS) {
      printSection(group.title);
      const cmdW = 22;
      for (const [cmd, desc] of group.rows) {
        const c = theme.fg("mint", padRight(cmd, cmdW));
        const d = theme.dim(truncateToWidth(desc, Math.max(20, lineW - cmdW - 2)));
        printLine(`  ${c} ${d}`);
      }
      printLine("");
    }

    printSection("TRY IT");
    const examples: [string, string][] = [
      ["/design", "CRBN PROTACs for BRD4 degradation"],
      ["/validate", "CC(=O)Nc1ccc(O)cc1"],
      ["/retro", "CC(=O)Nc1ccc(O)cc1"],
      ["/skill", "linker_generation"],
    ];
    for (const [cmd, rest] of examples) {
      printLine(`  ${theme.fg("cyan", cmd)} ${theme.dim(rest)}`);
    }
    printLine("");
    printLine(`  ${theme.dim("Tip: type a natural-language objective without a slash to run /design directly.")}`);
    printLine(`  ${theme.dim("Launch anywhere with:")} ${theme.fg("amber", `curl -fsSL ${LAUNCH_URL} | bash`)}`);
    printLine("");
    printLine(`  ${centerText(renderContract(lineW), lineW)}`);
    printLine("");
  }

  // ── About ──────────────────────────────────────────────────────

  private wrap(text: string, width: number): string[] {
    const words = text.split(/\s+/);
    const out: string[] = [];
    let cur = "";
    for (const w of words) {
      if (visibleWidth(cur) + w.length + 1 > width) {
        out.push(cur);
        cur = w;
      } else {
        cur = cur ? cur + " " + w : w;
      }
    }
    if (cur) out.push(cur);
    return out;
  }

  private para(text: string, width = 72): void {
    for (const l of this.wrap(text, width)) printLine(`  ${theme.semantic("text", l)}`);
    printLine("");
  }

  private showAbout(): void {
    const width = Math.min(process.stdout.columns ?? 110, 110);
    printLine("");
    printLine(`  ${theme.grad("PROTACXtend", "#9B94F0", "#5AB9CD")} ${theme.fg("cyan", `v${VERSION}`)}  ${theme.dim("· Targeted Protein Degradation Research Console")}`);
    printLine(`  ${theme.dim("─".repeat(Math.min(width - 4, 86)))}`);
    printLine("");

    printSection("WHAT IT IS");
    this.para("An evidence-grounded, tool-augmented AI agent platform for component-aware PROTAC design. Every step — evidence retrieval, molecular construction, ternary feasibility, degradation and cell-context prediction, ranking — is recorded with its input, output, evidence source, model version and limitation. Designed by Saveena Solanki & Ahuja Lab, IIIT Delhi.");
    printSection("THE SCIENTIFIC CONTRACT");
    this.para("PROTAC design is a coupled biological, structural and chemical optimization problem. PROTACXtend decomposes it into independently inspectable layers and walks a governed agent graph:");
    printLine(`  ${centerText(renderContract(Math.min(width - 6, 78)), Math.min(width - 6, 78))}`);
    printLine("");
    printKv("KNOW", "evidence retrieval & verification · targets · binders", 28);
    printKv("REASON", "warhead · E3 ligand · exit vector · applicability", 28);
    printKv("DESIGN", "linkers · assembly · validation · ADMET · feasibility", 28);
    printKv("DISCOVER", "ranking · hook effect · cooperativity · cell context", 28);
    printLine("");

    printSection("CAPABILITIES");
    const caps = [
      "Retrieval & verification — PubMed, Europe PMC, OpenAlex, Crossref, PROTAC-DB",
      "Component-aware design — warhead, E3 recruiter, exit-vector and linker search",
      "Ternary & ubiquitination feasibility — P4ward simulation, geometry proxies",
      "Hook-effect equilibrium, cooperativity (α) and DC50/Dmax prediction",
      "Cell-context conditioning on DepMap transcriptomics (cell-type selectivity)",
      "Multi-objective ranking with novelty, diversity and uncertainty control",
      "Reproducible outputs — Markdown report, CSV and JSON candidate dossiers",
    ];
    for (const c of caps) {
      printLine(`  ${theme.fg("mint", "•")} ${theme.dim(truncateToWidth(c, Math.min(width - 8, 84)))}`);
    }
    printLine("");

    printSection("UNDER THE HOOD");
    printKv("architecture", `${this.agentCount}-node core graph + 8 controlled-search extensions`, 16);
    printKv("engines", "RDKit · Chemprop · AutoDock Vina · ASKCOS · AiZynthFinder · P4ward", 16);
    printKv("catalog", `${this.skillsCount || "23+"} scientific skills · ${this.databaseCount || 14} API databases · ${this.toolCount} tools`, 16);
    printKv("model", process.env.PROTACXTEND_MODEL || "ollama/gpt-oss:20b (configurable, local)", 16);
    printKv("schemas", "typed Pydantic state + JSONL bridge protocol", 16);
    printLine("");

    printSection("VALIDATION & DOCS");
    printKv("status of truth", "config/scientific_status.yaml (machine readable)", 16);
    printKv("quick start", "documentation/GETTING_STARTED.md", 16);
    printKv("workflows", "documentation/WORKFLOWS.md", 16);
    printKv("web app", "site/index.html — static simulator + docs hub", 16);
    printLine("");

    printSection("PROJECT");
    printKv("website", theme.fg("cyan", SITE_URL), 16);
    printKv("repository", theme.fg("cyan", REPO_URL), 16);
    printKv("maintained by", "Saveena Solanki & Ahuja Lab (IIIT Delhi)", 16);
    printKv("license", "MIT", 16);
    printLine("");

    printSection("LAUNCH ANYWHERE");
    printLine(`  ${theme.dim("local")}   ${theme.fg("mint", "cd tui && node dist/index.js")}`);
    printLine(`  ${theme.dim("curl")}    ${theme.fg("amber", `curl -fsSL ${LAUNCH_URL} | bash`)}`);
    printLine("");
    printLine(`  ${centerText(renderContract(Math.min(width - 6, 78)), Math.min(width - 6, 78))}`);
    printLine("");
  }

  private showLaunch(): void {
    const row = (label: string, code: string) => {
      printLine(`  ${theme.fg("mint", label.padEnd(9))} ${theme.semantic("text", code)}`);
    };
    printLine("");
    printSection("ONE-LINE CURL LAUNCH");
    printLine("");
    row("install", `curl -fsSL ${LAUNCH_URL} | bash`);
    row("latest", `git pull && cd tui && npm install && npm run build && node dist/index.js`);
    printLine("");
    printSection("REQUIREMENTS");
    printLine(`  ${theme.semantic("text", "Node.js ≥ 18   ·   Python ≥ 3.10   ·   PROTACXtend python package (pip install -e .)")}`);
    printLine(`  ${theme.dim("Set PROTACXTEND_PYTHON to pick the python interpreter; PROTACXTEND_MODEL to pick the LLM.")}`);
    printLine("");
    printSection("LAUNCHER SOURCE");
    printLine(`  ${theme.dim("tui/launch.sh — clones/updates the repo, installs deps, builds, then runs the TUI.")}`);
    printLine("");
  }

  private showContract(): void {
    const width = process.stdout.columns ?? 80;
    printPanel("THE SCIENTIFIC CONTRACT", [
      renderContract(Math.min(width - 10, 66)),
      "",
      `${theme.dim("KNOW".padEnd(10))} scientific search, target resolution, binder evidence`,
      `${theme.dim("REASON".padEnd(10))} warhead decision, E3 selection, applicability`,
      `${theme.dim("DESIGN".padEnd(10))} linker generation, assembly, validation, ADMET`,
      `${theme.dim("DISCOVER".padEnd(10))} ranking, hook effect, cooperativity, cell context`,
    ], Math.min(width - 4, 74));
  }

  private showPlan(): void {
    printPanel("WORKFLOW PLAN", [
      "1. Parse the objective",
      "2. Resolve target — UniProt + AlphaFold",
      "3. Retrieve binders — ChEMBL + PubChem + BindingDB",
      "4. Choose warhead, E3 ligand, exit vector",
      "5. Generate linkers (multi-method engine)",
      "6. Construct and validate candidates",
      "7. Predict degradation, ADMET, novelty",
      "8. Rank, diversify, reflect, evolve",
      "9. Report — Markdown + CSV + JSON",
    ], 66);
  }

  private showStructure(args: string): void {
    if (args) {
      printInfo(`Ternary / structure analysis for: ${args}`);
      printInfo("Run /design with the same objective for a full feasibility pass.");
    } else {
      this.showUsage("/structure", "<objective>", "BRD4 CRBN ternary feasibility");
    }
  }

  private showLearn(args: string): void {
    printSection("ACTIVE LEARNING");
    if (args) printLine(`  ${theme.dim("objective")}  ${theme.semantic("text", args)}`);
    printLine(`  ${theme.dim("Feedback from past /design runs informs the next candidate generation.")}`);
    printLine(`  ${theme.dim("Add what to improve — e.g. “favour lower logP, penalise hERG alerts.”")}`);
  }

  // ── Simple mode (no backend) ───────────────────────────────────

  private runSimpleMode(): void {
    for (const line of renderSimpleHeader()) printLine(line);
    printLine("");
    printWarning("Python backend not available — running in simple mode.");
    printInfo("Type /help for commands; /about for project info; /quit to exit.");
    printLine("");

    this.rl = readline.createInterface({ input: process.stdin, output: process.stdout, prompt: this.prompt });
    this.running = true;
    this.rl.prompt();

    this.rl.on("line", async (input: string) => {
      const trimmed = input.trim();
      if (!trimmed) {
        this.rl?.prompt();
        return;
      }
      const cmd = trimmed.split(/\s+/)[0].toLowerCase();
      if (cmd === "/quit" || cmd === "/exit") {
        this.running = false;
        this.rl?.close();
        return;
      }
      if (cmd === "/help") this.showHelp();
      else if (cmd === "/about") this.showAbout();
      else if (cmd === "/launch") this.showLaunch();
      else if (cmd === "/contract") this.showContract();
      else if (cmd === "/plan") this.showPlan();
      else if (cmd === "/clear") {
        process.stdout.write("\x1b[2J\x1b[H");
        for (const l of renderSimpleHeader()) printLine(l);
      } else {
        printWarning(`Backend offline — ${trimmed.slice(0, 60)} not executed.`);
        printInfo("Install Python deps, then run from the repo: node dist/index.js");
      }
      this.rl?.prompt();
    });

    this.rl.on("close", () => {
      this.running = false;
    });
  }
}
