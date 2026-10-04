import { request } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DEV_API_BASE_URL, readRemoteVerifyToken, RUN_ID } from "./fixtures";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const AUTH_DIR = path.join(__dirname, ".auth");
const FIXTURES_PATH = path.join(__dirname, ".fixtures.json");

/**
 * Unlike frontend/e2e/global-setup.ts (which logs into fixed accounts
 * `flask seed-e2e` already created in a disposable local database), this
 * targets the real deployed dev database, which is never wiped -- so
 * fixtures are created here through the actual API, exactly like a real
 * user would, with RUN_ID-suffixed emails/usernames/URLs so repeated runs
 * never collide with data from a previous run or with anything you've
 * created by hand while manually testing the dev site.
 */
const FIXTURE_USERS = [
  { name: "alice", email: `e2e-dev-alice-${RUN_ID}@e2e.test`, username: `e2e_dev_alice_${RUN_ID}` },
  { name: "bob", email: `e2e-dev-bob-${RUN_ID}@e2e.test`, username: `e2e_dev_bob_${RUN_ID}` },
  { name: "carol", email: `e2e-dev-carol-${RUN_ID}@e2e.test`, username: `e2e_dev_carol_${RUN_ID}` },
];
const PASSWORD = "password123";

async function registerVerifyAndLogin(
  context: Awaited<ReturnType<typeof request.newContext>>,
  user: (typeof FIXTURE_USERS)[number],
) {
  const registerResponse = await context.post("/api/register", {
    data: { username: user.username, email: user.email, password: PASSWORD },
  });
  if (!registerResponse.ok()) {
    throw new Error(
      `global-setup (dev): register failed for ${user.email} (${registerResponse.status()}): ` +
        (await registerResponse.text()),
    );
  }

  const token = readRemoteVerifyToken(user.email);
  if (!token) {
    throw new Error(`global-setup (dev): no verify token found for ${user.email}`);
  }
  const verifyResponse = await context.post("/api/verify-email", { data: { token } });
  if (!verifyResponse.ok()) {
    throw new Error(
      `global-setup (dev): verify-email failed for ${user.email} (${verifyResponse.status()})`,
    );
  }

  const loginResponse = await context.post("/api/login", {
    data: { email: user.email, password: PASSWORD },
  });
  if (!loginResponse.ok()) {
    throw new Error(
      `global-setup (dev): login failed for ${user.email} (${loginResponse.status()})`,
    );
  }
}

export default async function globalSetup() {
  fs.mkdirSync(AUTH_DIR, { recursive: true });

  const contexts: Record<string, Awaited<ReturnType<typeof request.newContext>>> = {};
  for (const user of FIXTURE_USERS) {
    const context = await request.newContext({ baseURL: DEV_API_BASE_URL });
    await registerVerifyAndLogin(context, user);
    await context.storageState({ path: path.join(AUTH_DIR, `${user.name}.json`) });
    contexts[user.name] = context;
  }

  // A single private pattern, uploaded by alice and shared view-only with
  // bob -- one action that covers both this suite's needs: it makes the
  // pattern appear on bob's "Shared with Me" page, and share_pattern()
  // (see backend/app/patterns/routes.py) also fires a real in-app
  // "pattern_shared" notification for bob, which notifications.spec.ts
  // checks for. Carol gets neither, as the control case.
  const patternTitle = `E2E Dev Shared Pattern ${RUN_ID}`;
  const submitResponse = await contexts.alice.post("/api/patterns/submit", {
    data: {
      original_url: `https://example.com/e2e-dev-fixture-${RUN_ID}`,
      title: patternTitle,
      materials: "Test materials",
      instructions: { "Part 1": ["Step 1", "Step 2"] },
    },
  });
  if (!submitResponse.ok()) {
    throw new Error(`global-setup (dev): pattern submit failed (${submitResponse.status()})`);
  }
  const { pattern } = await submitResponse.json();

  const shareResponse = await contexts.alice.post(`/api/patterns/${pattern.id}/shares`, {
    data: { username: FIXTURE_USERS[1].username, can_edit: false },
  });
  if (!shareResponse.ok()) {
    throw new Error(`global-setup (dev): sharing pattern failed (${shareResponse.status()})`);
  }

  fs.writeFileSync(
    FIXTURES_PATH,
    JSON.stringify(
      {
        users: Object.fromEntries(FIXTURE_USERS.map((u) => [u.name, u])),
        sharedPattern: { id: pattern.id, title: patternTitle },
      },
      null,
      2,
    ),
  );

  for (const context of Object.values(contexts)) {
    await context.dispose();
  }
}
