import { expect, test } from "@playwright/test";

const API_BASE_URL = "http://localhost:5001";

/**
 * Named to sort alphabetically last -- Playwright (workers:1, see
 * playwright.config.ts) runs spec files in that order, and this test
 * MUST run after every other spec's real login/register traffic:
 * Flask-Limiter's login bucket (20/hour) is in-memory, shared, and keyed
 * by IP for the whole suite's run, so exhausting it here would 429 every
 * later real login attempt (e.g. guest-progress.spec.ts's own
 * register-then-login flow). It doesn't assume a specific starting
 * count either -- it loops until a 429 actually appears, bounded
 * generously above the bucket size so it's robust regardless of exactly
 * how much prior traffic (global-setup's 4 fixture logins, plus every
 * other file's own real logins) already spent.
 */
test("repeated failed logins eventually return 429", async ({ request }) => {
  let sawRateLimit = false;
  for (let attempt = 0; attempt < 25 && !sawRateLimit; attempt++) {
    const response = await request.post(`${API_BASE_URL}/api/login`, {
      data: { email: "nonexistent-e2e-user@e2e.test", password: "wrong" },
    });
    if (response.status() === 429) sawRateLimit = true;
  }
  expect(sawRateLimit).toBe(true);
});
