import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [tsconfigPaths(), react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      // The root layout only wires fonts and providers; the pages' parts are tested.
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/app/layout.tsx"],
      // `npm run test:coverage` fails below these shares of the code.
      thresholds: { lines: 80, statements: 80, functions: 80, branches: 75 },
    },
  },
});
