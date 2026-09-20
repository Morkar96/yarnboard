import { expect, request, test } from "@playwright/test";
import { readVerifyToken, PATTERNS } from "./fixtures";

const API_BASE_URL = "http://localhost:5001";
const STEP_LABEL = "Cast on 20 stitches.";

let englishPatternId: number;

test.beforeAll(async () => {
  const context = await request.newContext({ baseURL: API_BASE_URL });
  const response = await context.get("/api/patterns/community");
  const patterns = await response.json();
  const match = patterns.find((p: { title: string }) => p.title === PATTERNS.english);
  if (!match) throw new Error(`Seed pattern "${PATTERNS.english}" not found in community list`);
  englishPatternId = match.id;
  await context.dispose();
});

// Deliberately no storageState override -- this test starts logged out on
// purpose, to exercise the guest (localStorage-only) checklist path before
// an account exists.
test("checking off a step as a guest carries that progress into a new account", async ({ page }) => {
  await page.goto(`/pattern/${englishPatternId}`);
  await page.getByRole("checkbox", { name: STEP_LABEL }).check();

  const email = `e2e-guestmerge-${Date.now()}@e2e.test`;
  const username = `e2e_guestmerge_${Date.now()}`;

  await page.goto("/register");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();

  const token = readVerifyToken(email);
  expect(token).not.toBeNull();
  await page.goto(`/verify-email?token=${token}`);

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page.getByRole("button", { name: `Hi, ${username}` })).toBeVisible();

  await page.goto(`/pattern/${englishPatternId}`);
  await expect(page.getByRole("checkbox", { name: STEP_LABEL })).toBeChecked();
});
