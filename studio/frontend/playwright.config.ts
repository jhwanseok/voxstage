import { defineConfig } from "@playwright/test";
import path from "node:path";

// End-to-end test of the studio against its own backend (port 8712, database studio_e2e) and its own Vite server (5712),
// so it never touches the development data. It drives the installed Google Chrome: no browser download is needed.
//   npm run e2e        (Postgres must be running: python studio/dev.py starts it)
const win = process.platform === "win32";
const python = path.resolve(win ? "../backend/.venv/Scripts/python.exe" : "../backend/.venv/bin/python");

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:5712", channel: "chrome", trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: [
    { command: `"${python}" ../e2e/serve_api.py`, cwd: "../backend", url: "http://127.0.0.1:8712/api/v1/bots", timeout: 120_000, reuseExistingServer: false },
    { command: "npm run dev -- --host 127.0.0.1 --port 5712 --strictPort", env: { STUDIO_API_PORT: "8712" }, url: "http://127.0.0.1:5712/", timeout: 60_000, reuseExistingServer: false },
  ],
});
