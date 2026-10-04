import { expect, request, test } from "@playwright/test";
import { PATTERNS } from "./fixtures";

const API_BASE_URL = "http://localhost:5001";

let englishPatternId: number;
let hebrewPatternId: number;

test.beforeAll(async () => {
  const context = await request.newContext({ baseURL: API_BASE_URL });
  const response = await context.get("/api/patterns/community");
  const patterns = await response.json();
  const find = (title: string) => {
    const match = patterns.find((p: { title: string }) => p.title === title);
    if (!match) throw new Error(`Seed pattern "${title}" not found in community list`);
    return match.id as number;
  };
  englishPatternId = find(PATTERNS.english);
  hebrewPatternId = find(PATTERNS.hebrew);
  await context.dispose();
});

// No storageState needed -- pattern detail and Community are both public,
// and language is a pure client-side (localStorage) preference, not tied
// to an account. Every test starts from a fresh context, so the UI
// language always starts at its documented default (English) -- see
// getStoredLanguage() in frontend/src/i18n/index.ts.

test("toggling to Hebrew shows the reviewed Hebrew overlay for the English-primary pattern", async ({ page }) => {
  await page.goto(`/pattern/${englishPatternId}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(PATTERNS.english);
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");

  await page.getByRole("button", { name: "עברית" }).click();

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("תבנית לדוגמה באנגלית");
  await expect(page.getByText("מסרגות 4 מ״מ, חוט עבה")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");

  // Toggling back restores the pattern's own primary English content.
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(PATTERNS.english);
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
});

test("the English-primary pattern's Hebrew title also shows on the Community list", async ({ page }) => {
  await page.goto(`/pattern/${englishPatternId}`);
  await page.getByRole("button", { name: "עברית" }).click();

  await page.goto("/community");
  await expect(page.getByRole("link", { name: "תבנית לדוגמה באנגלית" })).toBeVisible();
  await expect(page.getByRole("link", { name: PATTERNS.english, exact: true })).not.toBeVisible();
});

test("the Hebrew-primary pattern shows its English overlay by default, and its own Hebrew content once toggled", async ({ page }) => {
  await page.goto(`/pattern/${hebrewPatternId}`);
  // Default UI language is English, and this pattern already has a
  // reviewed English overlay (title_en) -- translationForUiLanguage picks
  // that over the pattern's own Hebrew primary content.
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("E2E Hebrew Pattern");

  await page.getByRole("button", { name: "עברית" }).click();
  // No Hebrew overlay exists on this row (it IS the primary content), so
  // this falls back to the pattern's own primary Hebrew title.
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("תבנית עברית לבדיקה");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
});
