import { defineConfig } from "@playwright/test";

const baseURL = process.env.BASE_URL ?? "http://127.0.0.1:4174";

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  use: { baseURL },
  webServer: process.env.BASE_URL
    ? undefined
    : { command: "pnpm build && pnpm preview", url: baseURL, reuseExistingServer: false, timeout: 120_000 },
});
