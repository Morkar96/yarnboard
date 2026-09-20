import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Shared constants for the fixtures `flask seed-e2e` creates (see
 * backend/app/__init__.py) -- kept in one place so a spec file never
 * hardcodes a username/title that's drifted from the seed script.
 */
export const USERS = {
  admin: { email: "admin@e2e.test", username: "e2e_admin", password: "password123" },
  alice: { email: "alice@e2e.test", username: "e2e_alice", password: "password123" },
  bob: { email: "bob@e2e.test", username: "e2e_bob", password: "password123" },
  carol: { email: "carol@e2e.test", username: "e2e_carol", password: "password123" },
} as const;

export const PATTERNS = {
  english: "E2E English Pattern",
  hebrew: "תבנית עברית לבדיקה",
  privateShared: "E2E Private Shared Pattern",
  editableShared: "E2E Editable Shared Pattern",
  permissions: "E2E Permissions Pattern",
  unpublished: "E2E Unpublished Pattern",
  notificationOne: "E2E Notification Pattern One",
  notificationTwo: "E2E Notification Pattern Two",
} as const;

const BACKEND_DIR = path.join(__dirname, "..", "..", "backend");

/**
 * Shells out to `flask --app wsgi e2e-verify-token <email>` (see
 * backend/app/__init__.py) to read a just-registered user's verification
 * token without needing real email delivery, which is out of scope for
 * this suite. Returns null if the user doesn't exist or has no pending
 * token (the CLI command prints nothing in that case).
 */
export function readVerifyToken(email: string): string | null {
  const output = execFileSync(
    path.join(BACKEND_DIR, ".venv", "bin", "flask"),
    ["--app", "wsgi", "e2e-verify-token", email],
    {
      cwd: BACKEND_DIR,
      env: { ...process.env, DATABASE_URL: "sqlite:///e2e.db", FLASK_ENV: "development" },
      encoding: "utf-8",
    },
  ).trim();
  return output || null;
}
