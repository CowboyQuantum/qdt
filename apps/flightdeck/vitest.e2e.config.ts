import { defineConfig } from "vitest/config";

// Browser tests: drive the built app in the system Chrome (playwright-core). Run `pnpm build` first.
export default defineConfig({
  test: {
    environment: "node",
    include: ["e2e/**/*.test.ts"],
    testTimeout: 60_000,
    hookTimeout: 60_000,
  },
});
