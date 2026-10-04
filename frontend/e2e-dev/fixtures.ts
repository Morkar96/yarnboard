import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BACKEND_DIR = path.join(__dirname, "..", "..", "backend");

/**
 * Loads e2e-dev/.env (see .env.example) before anything below reads
 * process.env, so `E2E_REMOTE_DATABASE_URL` etc. can live in a local file
 * instead of needing `export`ed by hand every session. Optional --
 * loadEnvFile throws if the file doesn't exist, which is the common case
 * (nobody's required to use it, and it must never be committed -- see
 * the bare ".env" rule in the repo's root .gitignore).  This has to run
 * here, at the very top of the one module every entry point (the
 * Playwright config, global-setup, and the specs) imports from --
 * putting it in playwright.dev.config.ts instead would run too late,
 * since that file's own top-level import of this one already reads
 * DEV_BASE_URL/DEV_API_BASE_URL below before any of its other code runs.
 */
try {
  process.loadEnvFile(path.join(__dirname, ".env"));
} catch {
  // No .env file -- fall back to whatever's already in the environment.
}

/**
 * Base URLs for the actual deployed dev environment -- distinct from
 * frontend/e2e/'s suite, which only ever talks to the local dev servers.
 * Override via env if the Cloudflare/Render URLs ever change.
 */
export const DEV_BASE_URL = process.env.E2E_DEV_BASE_URL ?? "https://yarnboard-dev.morkar9696.workers.dev";
export const DEV_API_BASE_URL = process.env.E2E_DEV_API_BASE_URL ?? "https://yarnboard-dev-api.onrender.com";

/**
 * A per-run-unique suffix so repeated runs against the shared, never-wiped
 * dev database never collide on email/username/original_url uniqueness
 * constraints -- see global-setup.ts's decision to create fixtures
 * through the real API rather than reusing frontend/e2e/'s drop_all()
 * seed-e2e command, which would be destructive against a real database
 * that isn't a disposable local file.
 */
export const RUN_ID = `${Date.now()}`;

/**
 * Mirrors frontend/e2e/fixtures.ts's readVerifyToken, but points the
 * local `flask` CLI at the *remote* dev database via E2E_REMOTE_DATABASE_URL
 * instead of the local sqlite file -- this still runs the command on your
 * own machine (same technique used for the one-off production migrations
 * earlier), it just reads from Neon instead of a local file. Never commit
 * a real value for this env var; export it in your own shell only.
 */
export function readRemoteVerifyToken(email: string): string | null {
  const databaseUrl = process.env.E2E_REMOTE_DATABASE_URL;
  if (!databaseUrl) {
    throw new Error(
      "E2E_REMOTE_DATABASE_URL is not set -- export the dev database's " +
        "connection string in your own shell before running test:e2e:dev " +
        "(see README's \"Running the e2e suite against the deployed dev " +
        "environment\" section). Never commit this value.",
    );
  }
  const flaskBin = process.env.E2E_FLASK_BIN ?? path.join(BACKEND_DIR, ".venv", "bin", "flask");
  const output = execFileSync(
    flaskBin,
    ["--app", "wsgi", "e2e-verify-token", email],
    {
      cwd: BACKEND_DIR,
      env: { ...process.env, DATABASE_URL: databaseUrl, FLASK_ENV: "production" },
      encoding: "utf-8",
    },
  ).trim();
  return output || null;
}
