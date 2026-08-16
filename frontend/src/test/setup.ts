import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
// Initializes the global i18next instance (see src/i18n/index.ts) so
// every component's useTranslation() call resolves real English text in
// tests, the same as it would in the running app -- without this,
// components would render raw translation keys instead, breaking every
// test that asserts on visible text. No <I18nextProvider> needed in
// individual tests; react-i18next falls back to this default instance.
import "../i18n";

// Explicit rather than relying on @testing-library/react's automatic
// cleanup registration, which depends on a global `afterEach` that only
// exists if vitest's `test.globals` option is enabled (it isn't here).
afterEach(() => {
  cleanup();
});

// Node (22+) defines its own `localStorage` global that throws on access
// unless launched with --localstorage-file, and since jsdom's `window` IS
// globalThis in this test environment, that broken property shadows
// jsdom's own working localStorage implementation entirely -- neither
// `localStorage` nor `window.localStorage` works out of the box here.
// Replace it with a small in-memory Storage so code under test (e.g.
// utils/guestProgress.ts) behaves the same in tests as in a real browser.
class MemoryStorage implements Storage {
  private store = new Map<string, string>();
  get length() {
    return this.store.size;
  }
  clear() {
    this.store.clear();
  }
  getItem(key: string) {
    return this.store.has(key) ? this.store.get(key)! : null;
  }
  key(index: number) {
    return Array.from(this.store.keys())[index] ?? null;
  }
  removeItem(key: string) {
    this.store.delete(key);
  }
  setItem(key: string, value: string) {
    this.store.set(key, String(value));
  }
}

Object.defineProperty(globalThis, "localStorage", {
  value: new MemoryStorage(),
  writable: true,
  configurable: true,
});
