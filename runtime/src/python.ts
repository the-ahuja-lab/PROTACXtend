/**
 * Persistent Python science bridge — long-lived JSONL worker client.
 *
 * Spawns ONE `python -m protacxtend.runtime_worker` process and reuses it for
 * the whole Pi session (no fresh interpreter per tool call).
 */

import { spawn, type ChildProcess } from "node:child_process";
import { createInterface, type Interface } from "node:readline";
import { EventEmitter } from "node:events";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";

const here = dirname(fileURLToPath(import.meta.url));

function findProjectRoot(): string {
  let dir = resolve(here, "..");
  for (let i = 0; i < 8; i++) {
    if (existsSync(resolve(dir, "protacxtend", "__init__.py"))) return dir;
    dir = resolve(dir, "..");
  }
  return resolve(here, "..", "..");
}

export type WorkerResponse = Record<string, unknown> & {
  id?: string; type?: string; status?: string;
  summary?: string; data?: unknown; tool?: string;
  sources?: string[]; warnings?: string[]; limitations?: string[];
  evidence_type?: string;
};

export class PythonBridge extends EventEmitter {
  private proc: ChildProcess | null = null;
  private reader: Interface | null = null;
  private nextId = 1;
  private pending = new Map<string, { resolve: (v: WorkerResponse) => void; reject: (e: Error) => void }>();
  private closed = false;
  readonly root: string;

  constructor(root?: string) {
    super();
    this.root = root ?? findProjectRoot();
  }

  start(): Promise<void> {
    return new Promise((resolveReady, rejectReady) => {
      const python = process.env.PROTACXTEND_PYTHON ?? "python3";
      this.proc = spawn(python, ["-m", "protacxtend.runtime_worker"], {
        cwd: this.root,
        stdio: ["pipe", "pipe", "pipe"],
        env: { ...process.env, PYTHONUNBUFFERED: "1" },
      });
      this.closed = false;
      this.proc.on("error", (err) => rejectReady(err));
      this.proc.on("exit", (code) => {
        this.emit("exit", code);
        for (const p of this.pending.values()) p.reject(new Error(`worker exited (${code})`));
        this.pending.clear();
        this.ready = false;
      });
      this.proc.stderr?.on("data", (d: Buffer) => {
        const msg = d.toString().trim();
        if (msg) this.emit("stderr", msg);
      });
      this.reader = createInterface({ input: this.proc.stdout! });
      this.reader.on("line", (line: string) => {
        if (!line.trim()) return;
        let msg: WorkerResponse;
        try { msg = JSON.parse(line) as WorkerResponse; } catch { return; }
        if (msg.type === "bye") return;
        const id = String(msg.id ?? "");
        const waiter = id ? this.pending.get(id) : undefined;
        if (waiter) {
          this.pending.delete(id);
          if (msg.type === "error") waiter.reject(new Error(msg.summary ?? "worker error"));
          else waiter.resolve(msg);
        } else {
          this.emit("event", msg);
        }
      });
      // ready = first ping round-trip
      this.call("ping", {}).then(() => { this.ready = true; resolveReady(); },
                               (err) => rejectReady(err));
    });
  }

  private ready = false;

  async call(type: string, payload: Record<string, unknown>, timeoutMs = 300_000): Promise<WorkerResponse> {
    if (!this.proc || this.proc.exitCode !== null) await this.start();
    const id = String(this.nextId++);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`worker request '${type}' timed out`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (v) => { clearTimeout(timer); resolve(v); },
        reject: (e) => { clearTimeout(timer); reject(e); },
      });
      const line = JSON.stringify({ id, type, ...payload });
      this.proc!.stdin!.write(line + "\n");
    });
  }

  close(): void {
    if (this.closed || !this.proc) return;
    this.closed = true;
    try {
      this.proc.stdin!.write(JSON.stringify({ id: "bye", type: "shutdown" }) + "\n");
      this.proc.stdin!.end();
    } catch { /* ignore */ }
  }
}
