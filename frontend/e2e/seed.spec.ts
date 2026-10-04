import { test, expect } from "@playwright/test";

/**
 * Seed file for Playwright's planner/generator/healer agents (see
 * `npx playwright init-agents --loop=claude`, .claude/agents/playwright-test-*.md)
 * -- also doubles as a basic smoke test that the app actually boots
 * against the seeded e2e database (see `flask seed-e2e` in
 * backend/app/__init__.py, and `make e2e`).
 */
test.describe("Seed", () => {
  test("seed", async ({ page }) => {
    await page.goto("/community");
    await expect(page.getByRole("heading", { name: "Community Patterns" })).toBeVisible();
  });
});
