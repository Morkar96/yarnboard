import { request } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Logs in every fixture user (see `flask seed-e2e` in
 * backend/app/__init__.py) once via the API directly, and saves each
 * session as its own storageState file. Every spec except auth.spec.ts
 * loads the matching file via `test.use({ storageState: ... })` instead
 * of typing into the login form again -- AuthContext restores a session
 * purely from GET /api/profile reading the cookie on mount, so a
 * storageState-seeded cookie logs a user in on page load with no form
 * interaction. Keeping this traffic minimal also matters because every
 * request here counts against Flask-Limiter's shared 20-per-hour login
 * bucket, the same one auth.spec.ts's rate-limit test deliberately
 * exhausts -- see playwright.config.ts's workers:1 for why that ordering
 * is safe.
 */
const AUTH_DIR = path.join(__dirname, ".auth");
const API_BASE_URL = "http://localhost:5001";

const FIXTURE_USERS = [
  { name: "admin", email: "admin@e2e.test" },
  { name: "alice", email: "alice@e2e.test" },
  { name: "bob", email: "bob@e2e.test" },
  { name: "carol", email: "carol@e2e.test" },
];

export default async function globalSetup() {
  fs.mkdirSync(AUTH_DIR, { recursive: true });

  for (const { name, email } of FIXTURE_USERS) {
    const context = await request.newContext({ baseURL: API_BASE_URL });
    const response = await context.post("/api/login", {
      data: { email, password: "password123" },
    });
    if (!response.ok()) {
      throw new Error(`global-setup: login failed for ${email} (${response.status()})`);
    }
    await context.storageState({ path: path.join(AUTH_DIR, `${name}.json`) });
    await context.dispose();
  }
}
