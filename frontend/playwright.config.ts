import { defineConfig, devices } from "@playwright/test";

/**
 * Separate from vite.config.ts/vitest.config.ts -- this drives real
 * browsers against the two real dev servers (see Makefile's `e2e`
 * target), not a unit-test environment. `workers: 1` /
 * `fullyParallel: false` are deliberate, not a missed optimization: every
 * spec shares one long-lived backend process and one Flask-Limiter
 * in-memory rate-limit bucket keyed by IP (see e2e/auth.spec.ts's
 * rate-limit test, which must run after every other spec's login/register
 * traffic), and SQLite serializes writes at the file level regardless, so
 * there's no real parallelism to gain by risking that ordering.
 */
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
