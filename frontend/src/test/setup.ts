import "@testing-library/jest-dom/vitest";
import * as matchers from "vitest-axe/matchers";
import { expect, vi } from "vitest";

expect.extend(matchers);

// Pages fetch on mount; keep the network inert so the audit renders the
// initial/loading markup deterministically without a backend.
vi.stubGlobal(
  "fetch",
  vi.fn(() => new Promise(() => {})) as unknown as typeof fetch,
);

// jsdom has no canvas; stub getContext so axe-core's color-contrast check does
// not emit "Not implemented" noise during the audit.
HTMLCanvasElement.prototype.getContext = (() => null) as never;
