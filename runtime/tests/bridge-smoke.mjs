// Bridge smoke test (slice C/D): spawn the persistent Python worker once,
// run a real registered tool + catalog + session, then shut down.
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const worker = spawn(process.env.PROTACXTEND_PYTHON || "python3",
  ["-m", "protacxtend.runtime_worker"], {
    cwd: root, stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });
const rl = createInterface({ input: worker.stdout });
let nextId = 1;
const pending = new Map();

rl.on("line", (line) => {
  if (!line.trim()) return;
  const msg = JSON.parse(line);
  const w = pending.get(String(msg.id));
  if (w) { pending.delete(String(msg.id)); w(msg); }
});

function call(type, payload = {}, timeoutMs = 120000) {
  const id = String(nextId++);
  return new Promise((resolvePromise, reject) => {
    const t = setTimeout(() => { pending.delete(id); reject(new Error(`timeout ${type}`)); }, timeoutMs);
    pending.set(id, (m) => { clearTimeout(t); resolvePromise(m); });
    worker.stdin.write(JSON.stringify({ id, type, ...payload }) + "\n");
  });
}

const out = [];
try {
  const ping = await call("ping");
  out.push(`ping ok=${ping.data?.ok} home=${ping.data?.home}`);
  const cat = await call("catalog");
  out.push(`catalog tools=${cat.data.tools.length}`);
  const smiles = await call("tool", { tool: "inspect_smiles", args: { smiles: "CCO" } });
  out.push(`inspect_smiles → ${smiles.status} · ${smiles.evidence_type} · ${smiles.summary}`);
  const bad = await call("tool", { tool: "fake_tool", args: {} });
  out.push(`fake_tool → ${bad.type} (rejected, not fabricated)`);
  await call("session.save", { session_id: "smoke", payload: { objective: { target: "BRD4" } } });
  const resume = await call("session.resume", { session_id: "smoke" });
  out.push(`session.resume rows=${resume.data.rows.length}`);
  console.log(out.join("\n"));
} catch (err) {
  console.error("smoke failed:", err.message);
  process.exitCode = 1;
} finally {
  try { worker.stdin.write(JSON.stringify({ id: "bye", type: "shutdown" }) + "\n"); } catch {}
  worker.stdin.end();
  setTimeout(() => worker.kill(), 2000);
}
