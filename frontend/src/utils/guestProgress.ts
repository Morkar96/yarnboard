/**
 * Checklist progress for anonymous (not logged-in) viewers, kept entirely
 * in this browser's localStorage rather than synced to the backend --
 * there's no account to attach a UserPatternProgress row to. Shape
 * mirrors UserPatternProgress.completed_steps: {part: boolean[]}, indexed
 * in parallel with Pattern.instructions[part].
 *
 * localStorage access is wrapped in try/catch throughout: private
 * browsing / disabled storage / a full quota should degrade to "progress
 * just doesn't persist," never a crash. Goes through `window.localStorage`
 * specifically rather than the bare `localStorage` global -- in the
 * Vitest/jsdom test environment, Node's own experimental global
 * `localStorage` shadows jsdom's and throws on use, while
 * `window.localStorage` unambiguously resolves to jsdom's working one.
 */
const KEY_PREFIX = "yarnboard:guest-progress:";

export function getGuestProgress(patternId: number): Record<string, boolean[]> {
  try {
    const raw = window.localStorage.getItem(`${KEY_PREFIX}${patternId}`);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function setGuestStep(patternId: number, part: string, index: number, completed: boolean): void {
  try {
    const progress = getGuestProgress(patternId);
    const flags = [...(progress[part] ?? [])];
    flags[index] = completed;
    progress[part] = flags;
    window.localStorage.setItem(`${KEY_PREFIX}${patternId}`, JSON.stringify(progress));
  } catch {
    // Best-effort only -- see module docstring.
  }
}

/**
 * Every pattern this browser has guest progress for, keyed by pattern id
 * (as a string, since object keys are always strings -- the backend's
 * register() parses it back to int, see _merge_guest_progress). Used
 * once, at registration time (RegisterPage.tsx), to hand this browser's
 * pre-login progress off to the brand-new account so it isn't silently
 * lost the moment someone who's been using the app as a guest signs up.
 */
export function getAllGuestProgress(): Record<string, Record<string, boolean[]>> {
  const all: Record<string, Record<string, boolean[]>> = {};
  try {
    for (let i = 0; i < window.localStorage.length; i++) {
      const key = window.localStorage.key(i);
      if (!key || !key.startsWith(KEY_PREFIX)) continue;
      const patternId = key.slice(KEY_PREFIX.length);
      const raw = window.localStorage.getItem(key);
      if (raw) all[patternId] = JSON.parse(raw);
    }
  } catch {
    return {};
  }
  return all;
}

/** Clears every pattern's guest progress from localStorage -- called
 * right after a successful register-with-merge, so a second registration
 * later in the same browser (a different account) doesn't re-attach the
 * first guest session's progress to it. */
export function clearAllGuestProgress(): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < window.localStorage.length; i++) {
      const key = window.localStorage.key(i);
      if (key && key.startsWith(KEY_PREFIX)) keys.push(key);
    }
    keys.forEach((key) => window.localStorage.removeItem(key));
  } catch {
    // Best-effort only -- see module docstring.
  }
}
