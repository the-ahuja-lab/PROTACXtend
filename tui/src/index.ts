/**
 * PROTACXtend TUI Entry Point — Feynman-style terminal interface.
 *
 * Usage:
 *   protacxtend                          → launches TUI
 *   protacxtend tui                       → explicit TUI
 *   protacxtend tui "Design CRBN..."     → TUI + workflow
 */

import { ProtacXtendApp } from "./app.js";

const args = process.argv.slice(2);
const command = args[0];

async function main(): Promise<void> {
  const app = new ProtacXtendApp();

  // Check if a design request was passed
  if (command && command !== "tui" && !command.startsWith("-")) {
    // Treat the first arg as a design request
    // (handled after app starts)
    await app.start();
  } else if (command === "tui") {
    await app.start();
  } else {
    await app.start();
  }
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
