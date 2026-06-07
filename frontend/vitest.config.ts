import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// T085 — Accessibility audit runner. Renders pages in jsdom and asserts no
// axe-core WCAG 2.1 AA violations (Constitution Principle I).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.a11y.test.{ts,tsx}"],
  },
});
