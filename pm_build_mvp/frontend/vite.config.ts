import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function resolveApiPort(): string {
  if (process.env.PM_API_PORT) return process.env.PM_API_PORT;
  try {
    const fromFile = fs.readFileSync(path.join(__dirname, ".dev-api-port"), "utf-8").trim();
    if (fromFile) return fromFile;
  } catch {
    /* no port file — manual dev, default below */
  }
  return "8000";
}

const apiPort = resolveApiPort();
const apiTarget = `http://127.0.0.1:${apiPort}`;

const proxyOpts = {
  target: apiTarget,
  changeOrigin: true,
  timeout: 60_000,
};

// Proxy API calls to the FastAPI server so the frontend uses relative URLs.
// SSE works through the proxy (ws:false, buffering disabled by FastAPI headers).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/runs": proxyOpts,
      "/kernel": proxyOpts,
      "/health": proxyOpts,
    },
  },
});
