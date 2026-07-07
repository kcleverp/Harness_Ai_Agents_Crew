/**
 * Dev orchestrator — pick a free API port, start uvicorn, wait until ready, then Vite.
 *
 * PM_API_PORT     preferred start (default 8000); scans upward until free
 * PM_API_PORT_MAX max offset from preferred (default 50)
 */
import { spawn } from "child_process";
import fs from "fs";
import net from "net";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, "..");
const portFile = path.join(root, "frontend", ".dev-api-port");

function isPortFree(port) {
  return new Promise((resolve) => {
    const s = net.createServer();
    s.once("error", () => resolve(false));
    s.once("listening", () => s.close(() => resolve(true)));
    s.listen(port, "127.0.0.1");
  });
}

async function findFreePort(start, maxAttempts) {
  for (let p = start; p < start + maxAttempts; p++) {
    if (await isPortFree(p)) return p;
  }
  throw new Error(
    `No free port in range ${start}–${start + maxAttempts - 1}. ` +
      "Set PM_API_PORT to another base or free a port with netstat.",
  );
}

async function waitForApi(port, timeoutMs = 120_000) {
  const url = `http://127.0.0.1:${port}/health`;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(2000) });
      if (res.ok) return;
    } catch {
      /* API still starting (uvicorn --reload can take 10–30s on first import) */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(
    `API on port ${port} did not respond within ${timeoutMs / 1000}s. ` +
      "Check Python/uvicorn errors above.",
  );
}

const preferred = parseInt(process.env.PM_API_PORT || "8000", 10);
const maxAttempts = parseInt(process.env.PM_API_PORT_MAX || "50", 10);
const apiPort = await findFreePort(preferred, maxAttempts);

fs.writeFileSync(portFile, String(apiPort), "utf-8");

console.log(`[dev] API  http://127.0.0.1:${apiPort}  (starting…)`);

const childEnv = { ...process.env, PM_API_PORT: String(apiPort) };

const api = spawn(
  "python",
  [
    "-m", "uvicorn", "server.main:app",
    "--reload", "--host", "127.0.0.1", "--port", String(apiPort),
  ],
  { cwd: root, stdio: "inherit", shell: true, env: childEnv },
);

let web = null;
let stopping = false;

function shutdown(code = 0) {
  if (stopping) return;
  stopping = true;
  api.kill();
  if (web) web.kill();
  process.exit(code);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

api.on("exit", (code) => {
  if (code && code !== 0) shutdown(code ?? 1);
});

try {
  await waitForApi(apiPort);
  console.log(`[dev] API  ready on :${apiPort}`);
  console.log(`[dev] UI   http://localhost:5173  (proxy → :${apiPort})`);

  web = spawn("npm", ["run", "dev", "--prefix", "frontend"], {
    cwd: root,
    stdio: "inherit",
    shell: true,
    env: childEnv,
  });

  web.on("exit", (code) => {
    if (code && code !== 0) shutdown(code ?? 1);
  });
} catch (err) {
  console.error(`[dev] ${err.message}`);
  shutdown(1);
}
