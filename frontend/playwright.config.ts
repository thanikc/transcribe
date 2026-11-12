import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { chromium, defineConfig, devices } from "@playwright/test";

function resolveChromiumExecutable(): string | undefined {
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) {
    return process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  }
  try {
    const defaultPath = chromium.executablePath();
    if (defaultPath && fs.existsSync(defaultPath)) {
      return undefined;
    }
  } catch {
    /* fallback below */
  }
  const cacheDir = path.join(os.homedir(), ".cache", "ms-playwright");
  if (fs.existsSync(cacheDir)) {
    const dirs = fs
      .readdirSync(cacheDir)
      .filter((d) => d.startsWith("chromium-"))
      .sort()
      .reverse();
    for (const d of dirs) {
      const candidate = path.join(cacheDir, d, "chrome-linux64", "chrome");
      if (fs.existsSync(candidate)) {
        return candidate;
      }
    }
  }
  return undefined;
}

const executablePath = resolveChromiumExecutable();

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:8799",
    trace: "on-first-retry",
    launchOptions: executablePath ? { executablePath } : undefined,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: ".venv/bin/transcribe serve --fake --port 8799",
    cwd: "..",
    url: "http://127.0.0.1:8799/api/status",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
