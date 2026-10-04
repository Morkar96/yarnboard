import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

// Explicit rather than relying on @testing-library/react's automatic
// cleanup registration, which depends on a global `afterEach` that only
// exists if vitest's `test.globals` option is enabled (it isn't here).
afterEach(() => {
  cleanup();
});
