import { expect, test } from "@playwright/test";
import { readVerifyToken, USERS } from "./fixtures";

test.describe("registration and login", () => {
  test("a new user can register, verify their email, then log in", async ({ page }) => {
    const email = `e2e-newuser-${Date.now()}@e2e.test`;
    const username = `e2e_newuser_${Date.now()}`;

    await page.goto("/register");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("password123");
    await page.getByRole("button", { name: "Sign up" }).click();

    await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();

    const token = readVerifyToken(email);
    expect(token).not.toBeNull();

    await page.goto(`/verify-email?token=${token}`);
    await expect(page.getByRole("link", { name: "Go to login" })).toBeVisible();
    await page.getByRole("link", { name: "Go to login" }).click();

    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("password123");
    await page.getByRole("button", { name: "Log in", exact: true }).click();

    await expect(page.getByRole("button", { name: `Hi, ${username}` })).toBeVisible();
  });

  test("login with the wrong password shows an error and starts no session", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(USERS.alice.email);
    await page.getByLabel("Password").fill("not-the-real-password");
    await page.getByRole("button", { name: "Log in", exact: true }).click();

    await expect(page.getByText("Invalid email or password.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Log in" })).toBeVisible();
  });

  test("logout clears the session and hides authenticated nav items", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(USERS.bob.email);
    await page.getByLabel("Password").fill(USERS.bob.password);
    await page.getByRole("button", { name: "Log in", exact: true }).click();
    await expect(page.getByRole("button", { name: `Hi, ${USERS.bob.username}` })).toBeVisible();

    await page.getByRole("button", { name: `Hi, ${USERS.bob.username}` }).click();
    await page.getByRole("button", { name: "Log out" }).click();

    await expect(page.getByRole("link", { name: "Log in" })).toBeVisible();
  });
});

test.describe("submitting a pattern URL", () => {
  test.use({ storageState: "e2e/.auth/alice.json" });

  test("a URL resolving to a private/loopback address is rejected", async ({ page }) => {
    await page.goto("/submit");
    await page.getByLabel("Pattern URL").fill("http://127.0.0.1/internal-admin");
    const previewResponse = page.waitForResponse(
      (res) => res.url().endsWith("/api/patterns/preview") && res.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Preview" }).click();
    expect((await previewResponse).status()).toBe(502);

    // SubmitPatternPage auto-switches to the upload tab on ANY preview
    // failure so the user can work around it (see handleSubmit's catch) --
    // but that switch also unmounts the "link" mode's error Alert, so the
    // SSRF-rejection message itself is never actually shown to the user.
    // That's a real UX gap this test surfaces rather than papers over
    // (the 502 above is the authoritative proof of the actual rejection);
    // asserting the fallback's own visible behavior here instead.
    await expect(page.getByLabel("Saved HTML or PDF file")).toBeVisible();
    await expect(page.getByLabel("Pattern URL")).toHaveValue("http://127.0.0.1/internal-admin");
  });
});
