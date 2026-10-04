import { expect, request, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PATTERNS, USERS } from "./fixtures";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const API_BASE_URL = "http://localhost:5001";
const BACKEND_LOG_PATH = path.join(__dirname, "..", "..", "backend.log");

let notificationOneId: number;
let notificationTwoId: number;

test.beforeAll(async () => {
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
  notificationOneId = find(PATTERNS.notificationOne);
  notificationTwoId = find(PATTERNS.notificationTwo);
  await context.dispose();
});

test.use({ storageState: "e2e/.auth/alice.json" });

test("sharing a pattern creates an in-app notification the recipient can open and mark read", async ({
  page,
  browser,
}) => {
  await page.goto(`/pattern/${notificationOneId}`);
  await page.getByPlaceholder("Username").fill(USERS.bob.username);
  await page.getByRole("button", { name: "Share", exact: true }).click();
  await expect(page.getByText(USERS.bob.username)).toBeVisible();

  const bobContext = await browser.newContext({ storageState: "e2e/.auth/bob.json" });
  const bobPage = await bobContext.newPage();
  await bobPage.goto("/community");

  const bell = bobPage.getByRole("button", { name: "Notifications" });
  await expect(bell).toContainText("1");
  await bell.click();

  const item = bobPage.getByText(`shared "${PATTERNS.notificationOne}" with you.`);
  await expect(item).toBeVisible();
  await item.click();

  await expect(bobPage).toHaveURL(new RegExp(`/pattern/${notificationOneId}$`));
  await expect(bell).not.toContainText("1");
  await bobContext.close();
});

test("mark all read clears the unread badge", async ({ page, browser }) => {
  await page.goto(`/pattern/${notificationTwoId}`);
  await page.getByPlaceholder("Username").fill(USERS.bob.username);
  await page.getByRole("button", { name: "Share", exact: true }).click();
  await expect(page.getByText(USERS.bob.username)).toBeVisible();

  const bobContext = await browser.newContext({ storageState: "e2e/.auth/bob.json" });
  const bobPage = await bobContext.newPage();
  await bobPage.goto("/community");

  const bell = bobPage.getByRole("button", { name: "Notifications" });
  await expect(bell).toContainText("1");
  await bell.click();
  await bobPage.getByRole("button", { name: "Mark all read" }).click();

  await expect(bell).not.toContainText("1");
  await bobContext.close();
});

test("a disabled email channel suppresses the email send while in-app still fires", async ({
  page,
  browser,
}) => {
  await page.goto(`/pattern/${notificationTwoId}`);
  await page.getByPlaceholder("Username").fill(USERS.carol.username);
  await page.getByRole("button", { name: "Share", exact: true }).click();
  await expect(page.getByText(USERS.carol.username)).toBeVisible();

  const carolContext = await browser.newContext({ storageState: "e2e/.auth/carol.json" });
  const carolPage = await carolContext.newPage();
  await carolPage.goto("/community");
  await expect(carolPage.getByRole("button", { name: "Notifications" })).toContainText("1");
  await carolContext.close();

  const backendLog = fs.readFileSync(BACKEND_LOG_PATH, "utf-8");
  // e2e_bob (default settings, both channels on) got a real email attempt
  // from the previous test's share -- see backend/app/email.py's
  // log-instead-of-send fallback (RESEND_NOTIFICATIONS is unset for e2e).
  expect(backendLog).toContain(`would send email to ${USERS.bob.email}`);
  // e2e_carol has pattern_shared's email channel off (see `flask seed-e2e`
  // in backend/app/__init__.py) -- is_enabled() gates the call to
  // send_pattern_shared_email before it ever runs, so no attempt (logged
  // or otherwise) should exist for her.
  expect(backendLog).not.toContain(`would send email to ${USERS.carol.email}`);
});
