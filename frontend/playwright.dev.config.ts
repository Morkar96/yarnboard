import { defineConfig, devices } from "@playwright/test";
import { DEV_BASE_URL } from "./e2e-dev/fixtures";

/**
 * Runs against the real deployed dev environment (Cloudflare frontend +
 * the yarnboard-dev-api Render backend), not the local dev servers --
 * see playwright.config.ts for the local suite this is deliberately kept
 * separate from. Fixtures here are created non-destructively through the
 * real API (see global-setup.ts) since the dev database is never wiped,
 * unlike the local suite's disposable SQLite file. Not run in CI: it
 * depends on a live, always-on deployment and a real secret
 * (E2E_REMOTE_DATABASE_URL) that has no business being in a CI runner --
 * this is a manually-invoked `npm run test:e2e:dev`, run from your own
 * machine when you want to spot-check the actual dev deployment.
 *
 * video: "on" (not the local suite's default "off") is the whole point
 * of this config existing separately -- every run is recorded, so a
 * spot-check against real infra leaves behind something to actually look
 * at afterward, not just a pass/fail.
 */
export default defineConfig({
  testDir: "./e2e-dev",
  globalSetup: "./e2e-dev/global-setup.ts",
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL: DEV_BASE_URL,
    video: "on",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
