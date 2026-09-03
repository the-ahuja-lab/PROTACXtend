"""Command-line interface for PROTACXtend."""

from __future__ import annotations

import argparse
import os
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from protacxtend import __version__
from protacxtend.agents.runtime import run_protacpilot, summarize_run
from protacxtend.backend.main import run_workflow_from_request, summarize_state, write_outputs
from protacxtend.backend.mode_router import run_mode
from protacxtend.backend.schemas import model_to_dict

try:  # pragma: no cover - fallback is exercised when rich is unavailable.
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
except Exception:  # pragma: no cover
    Console = None
    Panel = None
    Table = None
    Text = None
    RICH_AVAILABLE = False

try:  # pragma: no cover - fallback is exercised when prompt_toolkit is unavailable.
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import WordCompleter

    PROMPT_TOOLKIT_AVAILABLE = True
except Exception:  # pragma: no cover
    PromptSession = None
    WordCompleter = None
    PROMPT_TOOLKIT_AVAILABLE = False


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CAPABILITIES: list[dict[str, str]] = [
    {
        "name": "Interactive terminal interface",
        "status": "available",
        "detail": "No-argument PROTACXtend opens a prompt with slash commands, scenarios, status, and run handoff.",
    },
    {
        "name": "Print/plan mode",
        "status": "available",
        "detail": "PROTACXtend -p \"Design ...\" returns a fast JSON plan and runtime estimate.",
    },
    {
        "name": "Scenario guide",
        "status": "available",
        "detail": "PROTACXtend scenarios shows common command patterns and expected runtime.",
    },
    {
        "name": "Scientific workflow run",
        "status": "available",
        "detail": "PROTACXtend \"Design ...\" runs the agentic PROTAC design workflow.",
    },
    {
        "name": "KNOW-REASON-DESIGN-DISCOVER contract",
        "status": "available",
        "detail": "PROTACXtend contract exposes scientific state, action cards, critique, dossiers, benchmarks, and model gates.",
    },
    {
        "name": "SMILES validation",
        "status": "available",
        "detail": "PROTACXtend validate --smiles CCO runs RDKit descriptors plus local scoring hooks.",
    },
    {
        "name": "terminal UI",
        "status": "available",
        "detail": "PROTACXtend (no args) or PROTACXtend tui opens a full-screen terminal UI with agent pipeline, model system, and live workflow log.",
    },
    {
        "name": "Frontend launcher",
        "status": "available",
        "detail": "PROTACXtend ui starts the Streamlit scientist workspace.",
    },
    {
        "name": "API launcher",
        "status": "available",
        "detail": "PROTACXtend api starts the FastAPI backend.",
    },
    {
        "name": "Retrosynthesis toolkits (ASKCOS / AiZynthFinder / RDKit+OpenNMT)",
        "status": "available",
        "detail": "Working engines behind run_retrosynthesis — protacxtend/tools/retrosynthesis_engines.py; "
                   "see scripts/retrosynthesis_toolkits_smoke.py and outputs/retrosynthesis_toolkits/evidence.json.",
    },
    {
        "name": "RPC/SDK parity",
        "status": "planned",
        "detail": "The backend functions exist, but a Pi-style stdin/stdout RPC protocol is not implemented yet.",
    },
]

SCENARIOS: list[dict[str, str]] = [
    {
        "name": "status",
        "command": "PROTACXtend status",
        "time": "1-3 seconds",
        "use": "Check installation, backend paths, and dependency availability.",
    },
    {
        "name": "validate",
        "command": 'PROTACXtend validate --smiles "CCO"',
        "time": "2-5 seconds",
        "use": "RDKit validation, descriptors, ADMET proxy, and degradation stub for one SMILES.",
    },
    {
        "name": "plan",
        "command": 'PROTACXtend -p "Design CRBN PROTACs for BRD4 degradation"',
        "time": "1-3 seconds",
        "use": "Pi-style print mode: show the planned workflow and estimated runtime without running design.",
    },
    {
        "name": "full_design",
        "command": 'PROTACXtend "Design CRBN PROTACs for BRD4 degradation"',
        "time": "2-8 minutes locally; longer if model loading or external tools are enabled",
        "use": "Run the full agentic scientific workflow.",
    },
    {
        "name": "deterministic_design",
        "command": 'PROTACXtend run "Design CRBN PROTACs for BRD4 degradation" --mode deterministic',
        "time": "2-6 minutes locally in the current repo state",
        "use": "Run the deterministic graph directly.",
    },
    {
        "name": "tui",
        "command": "PROTACXtend tui",
        "time": "Instant open; design jobs run inside the terminal UI",
        "use": "Launch the terminal interface with agent pipeline, model system, and live workflow log.",
    },
    {
        "name": "ui",
        "command": "PROTACXtend ui",
        "time": "5-15 seconds to boot; design jobs still take workflow time",
        "use": "Start the Streamlit scientist workspace.",
    },
    {
        "name": "api",
        "command": "PROTACXtend api",
        "time": "3-10 seconds to boot",
        "use": "Start the FastAPI backend.",
    },
]


def _console() -> Any:
    return Console() if RICH_AVAILABLE and Console is not None else None


def _print_json(payload: Any) -> None:
    print(json.dumps(model_to_dict(payload), indent=2))


def _request_from_parts(parts: list[str] | None, default: str = "") -> str:
    return " ".join(parts or []).strip() or default


def _estimate_for_request(request: str, mode: str = "agentic") -> dict[str, Any]:
    text = request.lower()
    wants_structure = any(term in text for term in ["structure", "ternary", "dock", "p4ward", "pose"])
    wants_many = any(term in text for term in ["100", "200", "large", "library", "screen"])
    base = "2-8 minutes"
    if mode == "deterministic":
        base = "2-6 minutes"
    if wants_structure:
        base = "10-60+ minutes if pose generation/docking is enabled; 2-8 minutes for proxy-only structural scoring"
    if wants_many:
        base = "8-30+ minutes depending on candidate count and model/tool availability"
    return {
        "request": request,
        "mode": mode,
        "estimated_runtime": base,
        "why": [
            "The command runs a scientific workflow, not a lightweight chat-only agent loop.",
            "Runtime depends on candidate count, RDKit/model loading, PROTAC-DB evidence lookup, TACK compatibility checks, and optional structural modeling.",
            "P4ward/Rosetta/docking-backed structural scenarios can move from minutes to hours.",
        ],
    }


def _print_plan(args: argparse.Namespace) -> int:
    request = _request_from_parts(args.request, "Design CRBN PROTACs for BRD4 degradation.")
    payload = _estimate_for_request(request, mode=args.mode)
    payload["workflow"] = [
        "parse objective",
        "bound search space",
        "select target binders, warheads, E3 ligands, exit vectors, and linkers",
        "construct and validate candidates",
        "score cell context, ADMET, novelty, applicability domain, degradation",
        "rank, diversify, review, evolve, select structural finalists",
        "score ternary/cooperativity/hook effect",
        "write report, memory, and active-learning update",
    ]
    _print_json(payload)
    return 0


def _render_banner() -> None:
    console = _console()
    if not console:
        print("PROTACXtend")
        print("Agentic PROTAC design CLI. Type /help or \\help, /capabilities, /scenarios, /status, /exit.")
        return
    title = Text("PROTACXtend", style="bold orange1")
    body = Text()
    body.append("Agentic PROTAC design terminal interface\n", style="bold")
    body.append("On a TTY, ", style="bold")
    body.append("PROTACXtend", style="bold green")
    body.append(" opens the terminal UI. In fallback mode:\n")
    body.append("Type a design request, or use slash/backslash commands: ")
    body.append("/help", style="bold cyan")
    body.append(" ")
    body.append("\\help", style="bold cyan")
    body.append(", ")
    body.append("/capabilities", style="bold cyan")
    body.append(", ")
    body.append("/scenarios", style="bold cyan")
    body.append(", ")
    body.append("/status", style="bold cyan")
    body.append(", ")
    body.append("/tui", style="bold green")
    body.append(", ")
    body.append("/exit", style="bold cyan")
    body.append(".")
    console.print(Panel(body, title=title, border_style="orange1"))


def _render_capabilities(json_output: bool = False) -> None:
    payload = {"capabilities": CAPABILITIES}
    if json_output or not RICH_AVAILABLE or Table is None:
        _print_json(payload)
        return
    console = _console()
    table = Table(title="PROTACXtend capabilities", show_lines=False)
    table.add_column("Capability", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    for item in CAPABILITIES:
        status_style = "green" if item["status"] == "available" else "yellow"
        table.add_row(item["name"], f"[{status_style}]{item['status']}[/{status_style}]", item["detail"])
    console.print(table)


def _render_scenarios(json_output: bool = False) -> None:
    payload = {"scenarios": SCENARIOS}
    if json_output:
        _print_json(payload)
        return
    if not RICH_AVAILABLE or Table is None:
        for item in SCENARIOS:
            print(f"{item['name']}: {item['command']}")
            print(f"  time: {item['time']}")
            print(f"  use:  {item['use']}")
        return
    console = _console()
    table = Table(title="PROTACXtend scenarios", show_lines=True)
    table.add_column("Scenario", style="bold orange1", no_wrap=True)
    table.add_column("Command", style="cyan")
    table.add_column("Typical time", style="green")
    table.add_column("Use")
    for item in SCENARIOS:
        table.add_row(item["name"], item["command"], item["time"], item["use"])
    console.print(table)


def _scenarios_command(args: argparse.Namespace) -> int:
    _render_scenarios(json_output=bool(args.json))
    return 0


def _capabilities_command(args: argparse.Namespace) -> int:
    _render_capabilities(json_output=bool(args.json))
    return 0


def _normalize_interactive_prompt(prompt: str) -> str:
    if prompt.startswith("\\"):
        return "/" + prompt[1:]
    return prompt


def _print_workflow_hint(command: str, request: str = "") -> None:
    topic = command.strip("/\\").lower()
    prompts = {
        "design": "Design and rank PROTAC candidates with bounded linker/E3/warhead search.",
        "evidence": "Retrieve PROTAC-DB, literature, affinity, degradation, permeability, and PK evidence.",
        "structure": "Score ternary feasibility, lysine reach, interface geometry, linker strain, and docking readiness.",
        "cellcontext": "Score target and E3 abundance in a cell-line-specific context.",
        "rank": "Run multi-objective ranking with degradation, ADMET, novelty, context, and uncertainty.",
        "learn": "Register experimental feedback for active-learning, validation, promotion, and rollback.",
        "report": "Create a scientist-facing report with candidates, caveats, evidence, and next experiments.",
    }
    payload = {
        "command": command,
        "description": prompts.get(topic, "PROTACXtend workflow shortcut."),
        "request": request or "No specific request supplied.",
        "next": f"Use /run {request}" if request else f"Use /{topic} <your task> or /run <your full design request>.",
    }
    _print_json(payload)


def _interactive_command() -> int:
    """Launch the terminal UI when on a TTY, else fallback."""
    # Startup question: which LLM backend (API vs Ollama)?
    import os as _os
    from protacxtend.llm.providers import USER_CONFIG_PATH
    if not _os.environ.get("PROTACPILOT_LLM_PROVIDER") and not USER_CONFIG_PATH.exists():
        try:
            from protacxtend.llm.setup import interactive_setup
            interactive_setup(ask=input, out=print)
        except Exception as exc:  # never block the UI on setup problems
            print(f"(llm setup skipped: {exc})")
    if sys.stdin.isatty():
        try:
            from protacxtend.tui.app import launch_tui
            launch_tui()
            return 0
        except ImportError as exc:
            print(f"TUI requires 'textual': {exc}", file=sys.stderr)
            print("Install with: pip install textual rich", file=sys.stderr)
        except Exception as exc:
            print(f"TUI failed: {exc}", file=sys.stderr)
    return _interactive_command_fallback()


def _interactive_command_fallback() -> int:
    """Fallback: simple text-based interactive mode when TUI is unavailable."""
    _render_banner()
    completer = None
    session = None
    if PROMPT_TOOLKIT_AVAILABLE and PromptSession is not None and WordCompleter is not None:
        completer = WordCompleter(
            [
                "/help",
                "\\help",
                "/status",
                "\\status",
                "/capabilities",
                "\\capabilities",
                "/scenarios",
                "\\scenarios",
                "/plan",
                "\\plan",
                "/run",
                "\\run",
                "/design",
                "\\design",
                "/evidence",
                "\\evidence",
                "/structure",
                "\\structure",
                "/cellcontext",
                "\\cellcontext",
                "/rank",
                "\\rank",
                "/learn",
                "\\learn",
                "/report",
                "\\report",
                "/contract",
                "\\contract",
                "/models",
                "\\models",
                "/benchmarks",
                "\\benchmarks",
                "/validate",
                "\\validate",
                "/tui",
                "\\tui",
                "/ui",
                "\\ui",
                "/api",
                "\\api",
                "/exit",
                "\\exit",
            ],
            ignore_case=True,
        )
        session = PromptSession(completer=completer)
    while True:
        try:
            if session is not None:
                prompt = session.prompt("PROTACXtend> ").strip()
            else:
                prompt = input("PROTACXtend> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not prompt:
            continue
        prompt = _normalize_interactive_prompt(prompt)
        if prompt in {"/exit", "exit", "quit", "/quit"}:
            return 0
        if prompt in {"/help", "help"}:
            build_parser().print_help()
            continue
        if prompt == "/status":
            _status_command(argparse.Namespace())
            continue
        if prompt == "/scenarios":
            _render_scenarios()
            continue
        if prompt == "/capabilities":
            _render_capabilities()
            continue
        if prompt.startswith("/plan "):
            _print_plan(argparse.Namespace(request=[prompt.removeprefix("/plan ").strip()], mode="agentic"))
            continue
        if prompt == "/contract" or prompt.startswith("/contract "):
            _mode_command("contract", argparse.Namespace(request=[prompt.removeprefix("/contract").strip()], section="summary"))
            continue
        if prompt == "/models" or prompt.startswith("/models "):
            _mode_command("contract", argparse.Namespace(request=[prompt.removeprefix("/models").strip()], section="models"))
            continue
        if prompt == "/benchmarks" or prompt.startswith("/benchmarks "):
            _mode_command("contract", argparse.Namespace(request=[prompt.removeprefix("/benchmarks").strip()], section="benchmarks"))
            continue
        shortcut = next(
            (
                item
                for item in ["/evidence", "/structure", "/cellcontext", "/rank", "/learn", "/report"]
                if prompt == item or prompt.startswith(f"{item} ")
            ),
            "",
        )
        if shortcut:
            _print_workflow_hint(shortcut, prompt.removeprefix(shortcut).strip())
            continue
        if prompt.startswith("/design "):
            prompt = prompt.removeprefix("/design ").strip()
        elif prompt == "/design":
            _print_workflow_hint("/design")
            continue
        if prompt.startswith("/validate "):
            _mode_command("validate", argparse.Namespace(smiles=prompt.removeprefix("/validate ").strip()))
            continue
        if prompt == "/tui":
            print("Launching terminal UI...")
            _tui_command(argparse.Namespace(request=[]))
            continue
        if prompt == "/ui":
            print("Starting Streamlit UI. Press Ctrl+C to stop it.")
            _ui_command(argparse.Namespace(host="0.0.0.0", port=8501, headless=True))
            continue
        if prompt == "/api":
            print("Starting FastAPI backend. Press Ctrl+C to stop it.")
            _api_command(argparse.Namespace(host="0.0.0.0", port=8001, reload=False))
            continue
        if prompt.startswith("/run "):
            prompt = prompt.removeprefix("/run ").strip()
        estimate = _estimate_for_request(prompt)
        console = _console()
        if console and Panel is not None:
            console.print(Panel(f"Estimated full workflow time: {estimate['estimated_runtime']}\nUse /plan {prompt} for a fast plan-only view.", title="Run estimate", border_style="yellow"))
        else:
            print(f"Estimated full workflow time: {estimate['estimated_runtime']}")
        answer = input("Run full workflow now? [y/N] ").strip().lower()
        if answer in {"y", "yes"}:
            _run_command(argparse.Namespace(request=[prompt], mode="agentic", run_id="", persistent=False, llm_enabled=False, json=False))
        else:
            print("Skipped. Use PROTACXtend -p \"...\" for a plan-only estimate.")


def _run_command(args: argparse.Namespace) -> int:
    request = _request_from_parts(args.request, "Design CRBN PROTACs for BRD4 degradation.")
    estimate = _estimate_for_request(request, mode=args.mode)
    print(
        f"PROTACXtend running {args.mode} workflow. Estimated time: {estimate['estimated_runtime']}. "
        "Use -p for instant plan-only mode.",
        file=sys.stderr,
    )
    config: dict[str, Any] = {
        "persistent": bool(args.persistent),
        "llm_enabled": bool(args.llm_enabled),
    }
    if args.run_id:
        config["run_id"] = args.run_id
    result = run_protacpilot(request, mode=args.mode, config=config)
    if args.json:
        _print_json(result)
    else:
        print(summarize_run(result))
        artifacts = result.get("artifacts") or {}
        if artifacts:
            _print_json({"artifacts": artifacts})
    return 0


def _design_command(args: argparse.Namespace) -> int:
    request = _request_from_parts(args.request, "Design CRBN PROTACs for BRD4 degradation.")
    state = run_workflow_from_request(request)
    paths = write_outputs(state, args.stem)
    _print_json({"summary": summarize_state(state), "outputs": paths})
    return 0


def _mode_command(mode: str, args: argparse.Namespace) -> int:
    payload: dict[str, Any] = {"mode": mode}
    if getattr(args, "request", None):
        payload["request"] = _request_from_parts(args.request)
    if getattr(args, "query", None):
        payload["query"] = _request_from_parts(args.query)
    for key in [
        "smiles",
        "target_uniprot_id",
        "e3_uniprot_id",
        "backend",
        "top_k",
        "section",
        "evidence_cutoff_date",
        "pose",
        "target_chain",
        "e3_chain",
        "candidate_id",
        "target",
        "e3",
        "cell",
        "poi",
        "action",
        "method_ids",
        "target_conc_nM",
        "e3_conc_nM",
        "kd_target_nM",
        "kd_e3_nM",
        "alpha",
        "degradation_rate",
        "resynthesis_rate",
        "predictions",
        "candidates",
        "feedback",
        "batch_size",
        "run_id",
    ]:
        value = getattr(args, key, None)
        if value not in (None, ""):
            payload[key] = value
    _print_json(run_mode(payload))
    return 0


def _tui_command(args: argparse.Namespace) -> int:
    """Launch the terminal UI."""
    try:
        from protacxtend.tui.app import launch_tui
        request = _request_from_parts(args.request) if args.request else None
        launch_tui(request)
        return 0
    except ImportError as exc:
        print(f"TUI requires 'textual': {exc}", file=sys.stderr)
        print("Install with: pip install textual rich", file=sys.stderr)
        return 1


def _ui_command(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(PROJECT_ROOT / "protacxtend" / "app" / "streamlit_app.py"),
        "--server.address",
        args.host,
        "--server.port",
        str(args.port),
    ]
    if args.headless:
        cmd += ["--server.headless", "true"]
    return subprocess.call(cmd, cwd=PROJECT_ROOT)


def _api_command(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "protacxtend.backend.api_routes:get_app",
        "--factory",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        cmd.append("--reload")
    return subprocess.call(cmd, cwd=PROJECT_ROOT)


def _status_command(args: argparse.Namespace) -> int:
    deps = ["rdkit", "pandas", "streamlit", "fastapi", "uvicorn", "pydantic", "sklearn"]
    payload = {
        "name": "PROTACXtend",
        "version": __version__,
        "project_root": str(PROJECT_ROOT),
        "frontend": {
            "command": "PROTACXtend ui",
            "url": "http://localhost:8501",
            "entrypoint": "protacxtend/app/streamlit_app.py",
        },
        "api": {
            "command": "PROTACXtend api",
            "url": "http://localhost:8001/docs",
            "entrypoint": "protacxtend/backend/api_routes.py",
        },
        "dependencies": {name: bool(importlib.util.find_spec(name)) for name in deps},
    }
    if getattr(args, "json", False) or not RICH_AVAILABLE or Table is None:
        _print_json(payload)
        return 0
    console = _console()
    table = Table(title="PROTACXtend status")
    table.add_column("Area", style="bold orange1")
    table.add_column("Value")
    table.add_row("Version", payload["version"])
    table.add_row("Project root", payload["project_root"])
    table.add_row("Frontend", f"{payload['frontend']['url']} ({payload['frontend']['command']})")
    table.add_row("API", f"{payload['api']['url']} ({payload['api']['command']})")
    for name, available in payload["dependencies"].items():
        table.add_row(f"Dependency: {name}", "available" if available else "missing")
    console.print(table)
    return 0




# ── LLM backend + assistant chat ───────────────────────────────────────

def _print_llm_status(out=print) -> None:
    from protacxtend.llm.setup import read_config
    info = read_config()
    h = info["health"]
    out("")
    out(f"  provider   {info['provider']}")
    out(f"  model      {info['model']}")
    out(f"  base_url   {info['base_url']}")
    out(f"  api_key    {'set' if info['api_key_set'] else 'not set'}")
    out(f"  health     {'OK (' + str(h.get('n_models')) + ' models visible)' if h.get('ok') else 'UNREACHABLE: ' + str(h.get('error', ''))}")
    if info.get("config_file"):
        out(f"  config     {info['config_file']}")
    out("")


def _llm_command(args: argparse.Namespace) -> int:
    from protacxtend.llm.providers import get_config
    if getattr(args, "setup", False):
        from protacxtend.llm.setup import interactive_setup
        interactive_setup(ask=input, out=print)
        _print_llm_status()
        return 0
    if args.provider or args.model or args.base_url or args.api_key:
        from protacxtend.llm.setup import apply_config
        try:
            apply_config(provider=args.provider or get_config().provider,
                         model=args.model or "",
                         base_url=args.base_url or "",
                         api_key=args.api_key or "")
        except ValueError as exc:
            print(f"llm: {exc}")
            return 1
    _print_llm_status()
    return 0


def _chat_command(args: argparse.Namespace) -> int:
    """Pi-style conversational scientific agent (tools → graph handoff)."""
    import os
    from protacxtend.agentic.chat_agent import ConversationalAgent, ClarificationNeeded
    from protacxtend.agentic.registry import TOOL_SPECS
    from protacxtend.llm.providers import USER_CONFIG_PATH, get_config

    if not os.environ.get("PROTACPILOT_LLM_PROVIDER") and not USER_CONFIG_PATH.exists():
        from protacxtend.llm.setup import interactive_setup
        interactive_setup(ask=input, out=print)

    cfg = get_config()
    agent = ConversationalAgent(cfg)

    def banner() -> str:
        from protacxtend.llm.chat_client import backend_banner
        return backend_banner(cfg)

    def print_run(run) -> None:
        for ev in run.events:
            print("  " + ev.render())

    def finish(run, newline=True) -> None:
        print_run(run)
        k = (run.summary or {}).get("kind")
        if k == "answer":
            print("\n" + str(run.summary.get("answer", "")))
        elif k == "handoff":
            print("\n" + str(run.summary.get("answer", "")))
        elif k == "clarification":
            print("\n" + str(run.summary.get("question", "")))
        elif k == "error":
            print("\n[error] " + str(run.summary.get("error", "unknown")))

    def fresh_agent() -> None:
        nonlocal agent
        agent = ConversationalAgent(get_config())

    message = " ".join(getattr(args, "message", None) or [])
    if message:
        try:
            run = agent.turn(message, ask=None if not sys.stdin.isatty() else input)
        except ClarificationNeeded as need:
            print("\nACTION REQUIRED — " + need.question)
            return 2
        finish(run)
        return 0

    print("")
    print("  PROTACXtend agent — " + banner())
    print("  ask scientifically · /llm switch backend · /tools · /agents · /status · /clear · /help · /exit")
    print("")
    while True:
        try:
            line = input("PROTACXtend> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            return 0
        if not line:
            continue
        low = line.lower()
        if low in ("/exit", "/quit", "exit", "quit"):
            return 0
        if low in ("/clear", "clear"):
            fresh_agent()
            print("(session cleared)")
            continue
        if low in ("/help", "help", "?"):
            print("  /llm /model set NAME   switch backend / model (shared config)")
            print("  /tools                 show the strict tool registry")
            print("  /agents                deterministic specialist agents (under the graph)")
            print("  /run <objective>       force a full workflow handoff")
            print("  /status                active provider + health")
            print("  /clear /exit           session controls")
            continue
        if low in ("/llm", "/model"):
            from protacxtend.llm.setup import interactive_setup
            interactive_setup(ask=input, out=print)
            fresh_agent()
            print("  → " + banner())
            continue
        if low.startswith("/model set ") or low.startswith("/models set "):
            name = line.split("set", 1)[1].strip()
            from protacxtend.llm.setup import apply_config
            try:
                apply_config(provider=cfg.provider, model=name)
                fresh_agent()
                print("  → model set to " + name)
            except Exception as exc:
                print("  model set failed: " + str(exc))
            continue
        if low in ("/models", "model") or low == "/model status":
            _print_llm_status()
            continue
        if low in ("/tools", "tools"):
            for sp in TOOL_SPECS:
                print(f"  {sp['name']:<28} [{sp['readiness']}] {sp['kind']} · {sp['evidence_type']}")
            continue
        if low in ("/agents", "agents"):
            print("  deterministic specialist agents live inside the SynGlue graph:")
            print("  Supervisor · Planner · Target · Binder · Warhead · E3 · Exit Vector · Linker ·")
            print("  Construction · Ternary · ADMET · Prediction · Cell Context · Ranking · Report")
            continue
        if low.startswith("/run "):
            line = "Design: " + line[5:].strip()
        text = line
        print("")
        try:
            run = agent.turn(text, ask=input)
        except ClarificationNeeded as need:
            print("\nACTION REQUIRED — " + need.question)
            continue
        finish(run)



def _runtime_command(args: argparse.Namespace) -> int:
    from protacxtend.pi_launcher import print_runtime_status
    return print_runtime_status()



def _pilot_command(args: argparse.Namespace) -> int:
    """PROTACpilot structural workflow — registered engines run, externals block honestly."""
    from protacxtend.workflows.pilot_runner import run_protacpilot_pipeline
    ctx = {"target": args.target or "", "e3": args.e3 or "", "protac_smiles": args.smiles or "",
           "objective": " ".join(args.request or [])}

    def emit(evt) -> None:
        line = f"[{evt.get('kind')}] {evt.get('stage','')} {evt.get('name')} ({evt.get('status')}) → {evt.get('summary')}"
        print("  " + line)

    result = run_protacpilot_pipeline(ctx, emit)
    print("")
    print(f"PROTACpilot pipeline: {result['status']}")
    print(f"  steps executed: {len(result['results'])}")
    if result.get("blocked_at"):
        print(f"  blocked at: {result['blocked_at']} (external engine not configured — NOT AVAILABLE, no fabrication)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="PROTACXtend",
        description="PROTACXtend command-line workspace for agentic PROTAC design.",
    )
    parser.add_argument("--version", action="version", version=f"PROTACXtend {__version__}")
    parser.add_argument("-p", "--print", action="store_true", help="Pi-style print mode: show plan and runtime estimate without running.")
    parser.add_argument("--mode", choices=["agentic", "deterministic"], default="agentic", help="Mode used by print mode or direct request.")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="Run the unified PROTACXtend runtime.")
    run.add_argument("request", nargs="*", help="Natural-language PROTAC design request.")
    run.add_argument("--mode", choices=["agentic", "deterministic"], default="agentic")
    run.add_argument("--run-id", default="", help="Optional stable run id.")
    run.add_argument("--persistent", action="store_true", help="Use persistent checkpointer for interrupt/resume.")
    run.add_argument("--llm-enabled", action="store_true", help="Enable configured LLM decision layer.")
    run.add_argument("--json", action="store_true", help="Print full JSON result.")
    run.set_defaults(func=_run_command)

    design = sub.add_parser("design", help="Run deterministic design and write report/CSV/JSON outputs.")
    design.add_argument("request", nargs="*", help="Natural-language PROTAC design request.")
    design.add_argument("--stem", default="protacxtend_run", help="Output filename stem.")
    design.set_defaults(func=_design_command)

    ask = sub.add_parser("ask", help="Search tools, databases, skills, and local literature context.")
    ask.add_argument("query", nargs="*", help="Question or search query.")
    ask.add_argument("--top-k", type=int, default=10)
    ask.set_defaults(func=lambda args: _mode_command("ask", args))

    validate = sub.add_parser("validate", help="Validate and score a PROTAC SMILES.")
    validate.add_argument("--smiles", required=True)
    validate.set_defaults(func=lambda args: _mode_command("validate", args))

    ternary = sub.add_parser("ternary", help="Run ternary-feasibility mode for one SMILES.")
    ternary.add_argument("--smiles", required=True)
    ternary.add_argument("--target-uniprot-id", default="")
    ternary.add_argument("--e3-uniprot-id", default="")
    ternary.add_argument("--backend", default="auto")
    ternary.set_defaults(func=lambda args: _mode_command("ternary", args))

    external = sub.add_parser("external", help="Show or launch external model/tool integration smoke jobs.")
    external.add_argument("--action", choices=["status", "launch", "results"], default="status")
    external.add_argument("--method-ids", default="", help="Comma-separated method IDs for --action launch.")
    external.set_defaults(func=lambda args: _mode_command("external", args))

    structure = sub.add_parser("structure", help="Score pose-backed ubiquitination geometry and cooperativity.")
    structure.add_argument("--pose", required=True, help="Ternary pose PDB file.")
    structure.add_argument("--smiles", default="", help="Candidate or linker SMILES for strain scoring.")
    structure.add_argument("--candidate-id", default="structure_input")
    structure.add_argument("--target-chain", default="")
    structure.add_argument("--e3-chain", default="")
    structure.set_defaults(func=lambda args: _mode_command("structure", args))

    dose = sub.add_parser("dose", help="Simulate ternary dose-response and hook-effect risk.")
    dose.add_argument("--target-conc-nM", type=float, default=100.0)
    dose.add_argument("--e3-conc-nM", type=float, default=100.0)
    dose.add_argument("--kd-target-nM", type=float, default=50.0)
    dose.add_argument("--kd-e3-nM", type=float, default=50.0)
    dose.add_argument("--alpha", type=float, default=1.0)
    dose.add_argument("--degradation-rate", type=float, default=1.0)
    dose.add_argument("--resynthesis-rate", type=float, default=0.15)
    dose.set_defaults(func=lambda args: _mode_command("dose", args))

    context = sub.add_parser("context", help="Run context-aware degradation predictor adapter.")
    context.add_argument("--smiles", required=True)
    context.add_argument("--candidate-id", default="context_input")
    context.add_argument("--e3", default="")
    context.add_argument("--cell", default="")
    context.add_argument("--poi", default="")
    context.set_defaults(func=lambda args: _mode_command("context", args))

    proteome = sub.add_parser("proteome", help="Score proteome/cell-context selectivity risk.")
    proteome.add_argument("--target", required=True)
    proteome.add_argument("--e3", required=True)
    proteome.add_argument("--cell", default="default")
    proteome.set_defaults(func=lambda args: _mode_command("proteome", args))

    learn = sub.add_parser("learn", help="Lock predictions or recommend next active-learning batch.")
    learn.add_argument("--action", choices=["lock", "recommend"], default="recommend")
    learn.add_argument("--predictions", default="[]", help="JSON list for --action lock.")
    learn.add_argument("--candidates", default="[]", help="JSON list for --action recommend.")
    learn.add_argument("--feedback", default="", help="Optional assay-feedback CSV path.")
    learn.add_argument("--batch-size", type=int, default=6)
    learn.add_argument("--run-id", default="")
    learn.set_defaults(func=lambda args: _mode_command("learn", args))

    contract = sub.add_parser("contract", help="Show KNOW-REASON-DESIGN-DISCOVER scientific contracts and dossiers.")
    contract.add_argument("request", nargs="*", help="Optional design request; omitted shows static contract registry.")
    contract.add_argument("--section", choices=["summary", "actions", "models", "benchmarks"], default="summary")
    contract.add_argument("--evidence-cutoff-date", default="")
    contract.set_defaults(func=lambda args: _mode_command("contract", args))

    tui = sub.add_parser("tui", help="Launch the terminal UI.")
    tui.add_argument("request", nargs="*", help="Optional design request to run immediately.")
    tui.set_defaults(func=_tui_command)

    ui = sub.add_parser("ui", help="Start the Streamlit frontend.")
    ui.add_argument("--host", default="0.0.0.0")
    ui.add_argument("--port", type=int, default=8501)
    ui.add_argument("--headless", action="store_true", default=True)
    ui.set_defaults(func=_ui_command)

    api = sub.add_parser("api", help="Start the FastAPI backend.")
    api.add_argument("--host", default="0.0.0.0")
    api.add_argument("--port", type=int, default=8001)
    api.add_argument("--reload", action="store_true")
    api.set_defaults(func=_api_command)

    pilot = sub.add_parser("pilot", help="Run the PROTACpilot structural workflow.")
    pilot.add_argument("request", nargs="*", help="Optional objective text (informational).")
    pilot.add_argument("--target", default="", help="Target, e.g. BRD4")
    pilot.add_argument("--e3", default="CRBN", help="E3 ligase, e.g. CRBN")
    pilot.add_argument("--smiles", default="", help="PROTAC/Warhead SMILES for decomposer/conformers")
    pilot.set_defaults(func=_pilot_command)

    runtime = sub.add_parser("runtime", help="Inspect the Pi runtime (status).")
    runtime.add_argument("action", nargs="?", default="status", choices=["status"])
    runtime.set_defaults(func=_runtime_command)

    llm = sub.add_parser("llm", help="Configure or inspect the LLM backend (API vs Ollama).")
    llm.add_argument("--setup", action="store_true", help="Interactive backend picker (API or Ollama).")
    llm.add_argument("--status", action="store_true", help="Show active backend and health.")
    llm.add_argument("--provider", default="", help="Provider: ollama|openai|openrouter|anthropic|google|openai_compatible")
    llm.add_argument("--model", default="")
    llm.add_argument("--base-url", default="")
    llm.add_argument("--api-key", default="")
    llm.set_defaults(func=_llm_command)

    chat = sub.add_parser("chat", help="Pi-style assistant chat with the configured LLM backend.")
    chat.add_argument("message", nargs="*", help="Optional one-shot question; omit for an interactive chat.")
    chat.set_defaults(func=_chat_command)

    status = sub.add_parser("status", help="Show local PROTACXtend runtime status.")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=_status_command)

    scenarios = sub.add_parser("scenarios", help="Show common PROTACXtend scenarios and runtime estimates.")
    scenarios.add_argument("--json", action="store_true")
    scenarios.set_defaults(func=_scenarios_command)

    capabilities = sub.add_parser("capabilities", help="Show PROTACXtend terminal and scientific capabilities.")
    capabilities.add_argument("--json", action="store_true")
    capabilities.set_defaults(func=_capabilities_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command_names = {
        "run",
        "llm",
        "chat",
        "runtime",
        "pilot",
        "design",
        "ask",
        "validate",
        "ternary",
        "contract",
        "external",
        "structure",
        "dose",
        "context",
        "proteome",
        "learn",
        "tui",
        "ui",
        "api",
        "status",
        "scenarios",
        "capabilities",
    }
    if not argv:
        if sys.stdin.isatty() and os.environ.get("PXT_PI", "1") != "0":
            from protacxtend.pi_launcher import resolve_pi_command, launch_pi
            if resolve_pi_command() is not None:
                return launch_pi()
        return _interactive_command()
    if "-p" in argv or "--print" in argv:
        mode = "agentic"
        cleaned: list[str] = []
        idx = 0
        while idx < len(argv):
            item = argv[idx]
            if item in {"-p", "--print"}:
                idx += 1
                continue
            if item == "--mode" and idx + 1 < len(argv):
                mode = argv[idx + 1]
                idx += 2
                continue
            cleaned.append(item)
            idx += 1
        if mode not in {"agentic", "deterministic"}:
            raise SystemExit(f"Invalid --mode for print mode: {mode}")
        return _print_plan(argparse.Namespace(request=cleaned, mode=mode))
    if argv and argv[0] not in command_names and not argv[0].startswith("-"):
        argv = ["run", *argv]
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
