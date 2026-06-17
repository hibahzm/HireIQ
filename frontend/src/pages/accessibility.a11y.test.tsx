/**
 * T085 — Accessibility audit (WCAG 2.1 AA, Constitution Principle I).
 *
 * Renders each user-facing page in jsdom and asserts zero axe-core violations.
 * Pages that read route params or fetch data are wrapped in MemoryRouter; the
 * network is stubbed (see src/test/setup.ts) so initial markup renders without
 * a backend.
 */
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { axe } from "vitest-axe";
import { describe, it, expect } from "vitest";

import LoginPage from "./auth/LoginPage";
import RegisterPage from "./auth/RegisterPage";
import JobApplicationPage from "./applications/JobApplicationPage";
import FeedbackReportPage from "./feedback/FeedbackReportPage";

const noop = () => {};

async function expectNoViolations(ui: React.ReactElement) {
  const { container } = render(ui);
  const results = await axe(container);
  expect(results).toHaveNoViolations();
}

describe("Accessibility (axe-core, WCAG 2.1 AA)", () => {
  it("LoginPage has no violations", async () => {
    await expectNoViolations(
      <LoginPage onSuccess={noop} onRegister={noop} onForgotPassword={noop} />
    );
  });

  it("RegisterPage has no violations", async () => {
    await expectNoViolations(<RegisterPage onSuccess={noop} onLogin={noop} />);
  });

  it("JobApplicationPage has no violations", async () => {
    await expectNoViolations(<JobApplicationPage jobId="test-job" />);
  });

  it("FeedbackReportPage (loading state) has no violations", async () => {
    await expectNoViolations(
      <MemoryRouter initialEntries={["/feedback/tok"]}>
        <Routes>
          <Route path="/feedback/:token" element={<FeedbackReportPage />} />
        </Routes>
      </MemoryRouter>,
    );
  });
});
