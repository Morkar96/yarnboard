import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// See shared-with-me.spec.ts for why this is read in a hook, not at
// module scope.
let fixtures: { sharedPattern: { id: number; title: string } };
test.beforeAll(() => {
  fixtures = JSON.parse(fs.readFileSync(path.join(__dirname, ".fixtures.json"), "utf-8"));
});

/**
 * The share in global-setup.ts already fired a real in-app "pattern_shared"
 * notification for bob server-side (see share_pattern in
 * backend/app/patterns/routes.py) -- this just confirms the UI surfaces
 * it correctly, rather than re-triggering the share here.
 *
 * Real email delivery is deliberately NOT checked here: unlike the local
 * suite (which reads a captured backend.log file), there's no equivalent
 * way to read the deployed dev-api service's Render logs from a test
 * runner without adding a Render API integration, which is out of scope
 * for this spot-check suite.
 */
test.describe("a real in-app notification from a pattern share", () => {
  test.use({ storageState: "e2e-dev/.auth/bob.json" });

  test("shows an unread badge, opens to the right pattern, and clears on click", async ({ page }) => {
    await page.goto("/community");

    const bell = page.getByRole("button", { name: "Notifications" });
    await expect(bell).toContainText("1");
    await bell.click();

    const item = page.getByText(`shared "${fixtures.sharedPattern.title}" with you.`);
    await expect(item).toBeVisible();
    await item.click();

    await expect(page).toHaveURL(new RegExp(`/pattern/${fixtures.sharedPattern.id}$`));
    await expect(bell).not.toContainText("1");
  });
});
