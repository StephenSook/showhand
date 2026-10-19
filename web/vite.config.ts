import { defineConfig } from "vitest/config";

export default defineConfig({
  // three.js alone is most of the bundle; one 650 kB chunk is expected.
  build: { target: "es2022", sourcemap: true, chunkSizeWarningLimit: 800 },
  test: { include: ["tests/**/*.test.ts"], environment: "node" },
});
