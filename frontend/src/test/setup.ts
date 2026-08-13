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
