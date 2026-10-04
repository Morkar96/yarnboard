import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Read inside a hook, not at module scope -- this file is imported during
// test collection (e.g. `playwright test --list`) before globalSetup has
// necessarily run, and a top-level read would crash collection itself
// rather than just failing a test.
let fixtures: { sharedPattern: { id: number; title: string } };
test.beforeAll(() => {
  fixtures = JSON.parse(fs.readFileSync(path.join(__dirname, ".fixtures.json"), "utf-8"));
});

test.describe("a pattern shared with me", () => {
  test.use({ storageState: "e2e-dev/.auth/bob.json" });

  test("appears on the Shared with Me page, and the pattern itself is visible", async ({ page }) => {
    await page.goto("/shared-with-me");
    await expect(page.getByRole("heading", { name: "Shared with Me" })).toBeVisible();

    const card = page.getByRole("link", { name: fixtures.sharedPattern.title });
    await expect(card).toBeVisible();

    // Not just that the card renders -- follow it through and confirm the
    // pattern's actual content loads, matching the original ask that "the
    // patterns themselves are visible", not just a link to them.
    await card.click();
    await expect(page).toHaveURL(new RegExp(`/pattern/${fixtures.sharedPattern.id}$`));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(fixtures.sharedPattern.title);
    await expect(page.getByText("Test materials")).toBeVisible();
  });
});

test.describe("nobody has shared anything with me", () => {
  test.use({ storageState: "e2e-dev/.auth/carol.json" });

  test("shows the empty state, not another user's shared pattern", async ({ page }) => {
    await page.goto("/shared-with-me");
    await expect(page.getByText("Nobody has shared a pattern with you yet.")).toBeVisible();
    await expect(page.getByText(fixtures.sharedPattern.title)).not.toBeVisible();
  });
});
