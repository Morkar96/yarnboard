import { expect, request, test } from "@playwright/test";
import { PATTERNS } from "./fixtures";

const API_BASE_URL = "http://localhost:5001";

let permissionsPatternId: number;

test.beforeAll(async () => {
  // Community list is public -- no auth needed to resolve the fixture
  // pattern's id, which none of the seed data hardcodes on the frontend
  // side (see backend/app/__init__.py's seed-e2e command).
  const context = await request.newContext({ baseURL: API_BASE_URL });
  const response = await context.get("/api/patterns/community");
  const patterns = await response.json();
  const match = patterns.find((p: { title: string }) => p.title === PATTERNS.permissions);
  if (!match) throw new Error(`Seed pattern "${PATTERNS.permissions}" not found in community list`);
  permissionsPatternId = match.id;
  await context.dispose();
});

test.describe("the uploader (e2e_bob)", () => {
  test.use({ storageState: "e2e/.auth/bob.json" });

  test("can edit their own pattern", async ({ page }) => {
    await page.goto(`/pattern/${permissionsPatternId}/edit`);
    await expect(page.getByRole("heading", { name: "Edit Pattern" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Save Changes" })).toBeVisible();
  });
});

test.describe("an unrelated logged-in user (e2e_carol)", () => {
  test.use({ storageState: "e2e/.auth/carol.json" });

  test("is forbidden from editing", async ({ page }) => {
    await page.goto(`/pattern/${permissionsPatternId}`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(PATTERNS.permissions);
    await expect(page.getByRole("link", { name: "Edit" })).not.toBeVisible();

    await page.goto(`/pattern/${permissionsPatternId}/edit`);
    await expect(page.getByText("You don't have permission to edit this pattern.")).toBeVisible();
  });
});

test.describe("an admin (e2e_admin)", () => {
  test.use({ storageState: "e2e/.auth/admin.json" });

  test("can edit a pattern they didn't upload", async ({ page }) => {
    await page.goto(`/pattern/${permissionsPatternId}/edit`);
    await expect(page.getByRole("heading", { name: "Edit Pattern" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Save Changes" })).toBeVisible();
  });
});
