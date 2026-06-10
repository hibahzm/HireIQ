import { matchPath } from "react-router-dom";

export interface Crumb {
  label: string;
  to?: string;
}

// Ordered most-specific first. Each entry maps a route pattern to a crumb
// trail; `:param` placeholders are filled from the matched params.
const ROUTES: Array<{ pattern: string; crumbs: (p: Record<string, string | undefined>) => Crumb[] }> = [
  { pattern: "/overview", crumbs: () => [{ label: "Overview" }] },
  { pattern: "/jobs", crumbs: () => [{ label: "Jobs" }] },
  {
    pattern: "/jobs/:jobId/setup",
    crumbs: () => [{ label: "Jobs", to: "/jobs" }, { label: "Job setup" }],
  },
  {
    pattern: "/jobs/:jobId/applications",
    crumbs: () => [{ label: "Jobs", to: "/jobs" }, { label: "Applications" }],
  },
  {
    pattern: "/jobs/:jobId/analytics",
    crumbs: () => [{ label: "Jobs", to: "/jobs" }, { label: "Analytics" }],
  },
  {
    pattern: "/jobs/:jobId/evaluations",
    crumbs: (p) => [
      { label: "Jobs", to: "/jobs" },
      { label: "Applications", to: `/jobs/${p.jobId}/applications` },
      { label: "Shortlist" },
    ],
  },
  {
    pattern: "/applications/:applicationId",
    crumbs: () => [{ label: "Jobs", to: "/jobs" }, { label: "Application" }],
  },
  {
    pattern: "/evaluations/:evaluationId",
    crumbs: () => [{ label: "Shortlist" }, { label: "Evaluation" }],
  },
  { pattern: "/users", crumbs: () => [{ label: "Team" }] },
];

export function crumbsFor(pathname: string): Crumb[] {
  for (const route of ROUTES) {
    const match = matchPath(route.pattern, pathname);
    if (match) return route.crumbs(match.params);
  }
  return [{ label: "HireIQ" }];
}
