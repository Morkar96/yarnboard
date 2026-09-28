import { expect, request, test } from "@playwright/test";
import { PATTERNS } from "./fixtures";

const API_BASE_URL = "http://localhost:5001";

let privateSharedId: number;
let editableSharedId: number;
let unpublishedId: number;

test.beforeAll(async () => {
  // /api/patterns/mine requires the uploader's own session -- these three
  // fixtures are all private, so they never appear in the public
  // community list permissions.spec.ts resolves ids from.
  const context = await request.newContext({
    baseURL: API_BASE_URL,
    storageState: "e2e/.auth/alice.json",
  });
  const response = await context.get("/api/patterns/mine");
  const patterns = await response.json();
  const find = (title: string) => {
    const match = patterns.find((p: { title: string }) => p.title === title);
    if (!match) throw new Error(`Seed pattern "${title}" not found in e2e_alice's uploads`);
    return match.id as number;
  };
  privateSharedId = find(PATTERNS.privateShared);
  editableSharedId = find(PATTERNS.editableShared);
  unpublishedId = find(PATTERNS.unpublished);
  await context.dispose();
});

test.describe("visibility to an unrelated user", () => {
  test.use({ storageState: "e2e/.auth/carol.json" });

  test("a private, unshared pattern is invisible", async ({ page }) => {
    await page.goto(`/pattern/${unpublishedId}`);
    await expect(page.getByText("Pattern not found.")).toBeVisible();
  });
});

test.describe("publish / unpublish", () => {
  test.use({ storageState: "e2e/.auth/alice.json" });

  test("publishing makes the pattern visible on the Community page", async ({ page }) => {
    await page.goto(`/pattern/${unpublishedId}`);
    await page.getByRole("button", { name: "Publish to Community" }).click();
    await page.getByLabel("I understand this pattern will be published publicly.").check();
    await page.getByRole("button", { name: "Confirm & Publish" }).click();

    await expect(page.getByText("Public", { exact: true })).toBeVisible();

    await page.goto("/community");
    await expect(page.getByRole("link", { name: PATTERNS.unpublished })).toBeVisible();
  });

  test("unpublishing removes it from Community but keeps uploader access", async ({ page }) => {
    page.once("dialog", (dialog) => dialog.accept());
    await page.goto(`/pattern/${unpublishedId}`);
    await page.getByRole("button", { name: "Unpublish" }).click();

    await expect(page.getByText("Private", { exact: true })).toBeVisible();

    await page.goto("/community");
    await expect(page.getByRole("link", { name: PATTERNS.unpublished })).not.toBeVisible();

    await page.goto(`/pattern/${unpublishedId}`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(PATTERNS.unpublished);
  });
});

test.describe("a view-only share (e2e_bob on the private-shared pattern)", () => {
  test.use({ storageState: "e2e/.auth/bob.json" });

  test("can view but not edit", async ({ page }) => {
    await page.goto(`/pattern/${privateSharedId}`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(PATTERNS.privateShared);
    await expect(page.getByRole("link", { name: "Edit" })).not.toBeVisible();

    await page.goto(`/pattern/${privateSharedId}/edit`);
    await expect(page.getByText("You don't have permission to edit this pattern.")).toBeVisible();
  });
});

test.describe("an edit-level share (e2e_bob on the editable-shared pattern)", () => {
  test.use({ storageState: "e2e/.auth/bob.json" });

  test("can view and edit", async ({ page }) => {
    await page.goto(`/pattern/${editableSharedId}/edit`);
    await expect(page.getByRole("heading", { name: "Edit Pattern" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Save Changes" })).toBeVisible();
  });
});

test.describe("removing a share", () => {
  test.use({ storageState: "e2e/.auth/alice.json" });

  test("revokes the shared user's access", async ({ page }) => {
    await page.goto(`/pattern/${privateSharedId}`);
    await expect(page.getByText("e2e_bob")).toBeVisible();
    await page.getByRole("button", { name: "Remove" }).click();
    await expect(page.getByText("Not shared with anyone yet.")).toBeVisible();
  });
});

test.describe("after the share is removed", () => {
  test.use({ storageState: "e2e/.auth/bob.json" });

  test("e2e_bob can no longer view the pattern", async ({ page }) => {
    await page.goto(`/pattern/${privateSharedId}`);
    await expect(page.getByText("Pattern not found.")).toBeVisible();
  });
});
