import { defineConfig, configDefaults } from "vitest/config";
import react from "@vitejs/plugin-react";

// Separate from vite.config.ts (the production build config) so test-only
// setup never risks affecting `npm run build`.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Vitest's default include glob isn't scoped to src/, so without this
    // it would also pick up frontend/e2e/*.spec.ts and frontend/e2e-dev/
    // *.spec.ts and try to run Playwright specs as Vitest tests (those
    // import `test`/`expect` from @playwright/test, a different,
    // incompatible test runner). Both have their own runner -- see
    // playwright.config.ts/playwright.dev.config.ts and `make e2e`/
    // `npm run test:e2e:dev`.
    exclude: [...configDefaults.exclude, "e2e/**", "e2e-dev/**"],
  },
});
