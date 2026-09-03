#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# PROTACXtend TUI — one-line launcher (curl → run, anywhere)
#
#   curl -fsSL https://raw.githubusercontent.com/the-ahuja-lab/PROTACXtend/main/tui/launch.sh | bash
#
# What it does:
#   1. checks Node ≥ 18 and Python ≥ 3.10
#   2. clones/updates the PROTACXtend repo into ${PROTACXTEND_DIR:-~/protacxtend}
#   3. installs the python package in editable mode (skippable)
#   4. installs TUI node deps + builds dist/
#   5. launches the TUI, forwarding any extra args
#
# Environment overrides:
#   PROTACXTEND_DIR        install location            (default ~/protacxtend)
#   PROTACXTEND_PYTHON     python interpreter          (default python3)
#   PROTACXTEND_SKIP_PIP   skip pip install -e .       (default 0)
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

REPO_URL="https://github.com/the-ahuja-lab/PROTACXtend.git"
DEST="${PROTACXTEND_DIR:-$HOME/protacxtend}"
PYTHON="${PROTACXTEND_PYTHON:-python3}"

# ── colours ──
C_RESET=$'\033[0m'; C_VIOLET=$'\033[1;38;2;142;134;232m'; C_MINT=$'\033[1;38;2;111;227;190m'; C_CYAN=$'\033[1;38;2;90;185;205m'; C_AMBER=$'\033[1;38;2;232;180;107m'; C_RED=$'\033[1;38;2;255;122;147m'
banner() { echo "${C_VIOLET}──────────────────────────────────────────────────────────${C_RESET}"; }

banner
echo "${C_VIOLET}  PROTACXtend — one-line launcher${C_RESET}"
banner
echo ""

# ── 1. prerequisites ──
echo "${C_CYAN}▸ checking prerequisites${C_RESET}"
if ! command -v node &>/dev/null || [ "$(node -e 'console.log(process.versions.node.split(".")[0])')" -lt 18 ]; then
  echo "${C_RED}✗ Node.js ≥ 18 required. Install from https://nodejs.org${C_RESET}"; exit 1
fi
if ! command -v "$PYTHON" &>/dev/null; then
  echo "${C_RED}✗ $PYTHON not found. Install Python ≥ 3.10 first.${C_RESET}"; exit 1
fi
echo "${C_MINT}✓ node $(node -v) · $PYTHON $("$PYTHON" -V 2>&1 | awk '{print $2}')${C_RESET}"

# ── 2. repo ──
echo "${C_CYAN}▸ ensuring PROTACXtend at ${C_RESET}${C_AMBER}$DEST${C_RESET}"
if [ ! -d "$DEST/.git" ]; then
  mkdir -p "$DEST"
  git clone --depth 1 "$REPO_URL" "$DEST"
else
  echo "${C_MINT}✓ repository present — pulling latest${C_RESET}"
  (cd "$DEST" && git pull --ff-only) || echo "${C_AMBER}⚠ pull failed — continuing with local copy${C_RESET}"
fi
cd "$DEST"

# ── 3. python package ──
if [ "${PROTACXTEND_SKIP_PIP:-0}" != "1" ]; then
  echo "${C_CYAN}▸ installing python package (editable)${C_RESET}"
  if ! "$PYTHON" -c "import protacxtend" 2>/dev/null; then
    "$PYTHON" -m pip install -e . --quiet || echo "${C_AMBER}⚠ pip install failed — bridge needs the package; see documentation/GETTING_STARTED.md${C_RESET}"
  else
    echo "${C_MINT}✓ protacxtend already importable${C_RESET}"
  fi
fi

# ── 4. TUI build ──
echo "${C_CYAN}▸ installing TUI dependencies + build${C_RESET}"
cd tui
[ -d node_modules ] || npm install --no-audit --no-fund >/dev/null 2>&1
[ -f dist/index.js ] || npm run build >/dev/null 2>&1
echo "${C_MINT}✓ TUI ready${C_RESET}"
banner
echo "${C_VIOLET}  launch — type /help · /about · /skills · or a design objective${C_RESET}"
banner
echo ""

# ── 5. run ──
exec node dist/index.js "$@"
