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
