import type { CandidateApplication } from "../../services/api";
import { BriefcaseIcon } from "../../components/ui/icons";

export type Notify = (b: { kind: "ok" | "err"; text: string }) => void;

/** Shared empty-state icon for the candidate tabs. */
export const briefcaseIcon = <BriefcaseIcon className="h-7 w-7" />;

/** Whether an application's interview invite is still actionable.
 * Once the interview is done (evaluated / feedback available) it isn't — only
 * the feedback should show. */
export function interviewActive(a: CandidateApplication): boolean {
  if (!a.interview_token) return false;
  if (a.feedback_token || a.status === "evaluated") return false;
  if (!a.interview_token_expires_at) return true;
  return new Date(a.interview_token_expires_at).getTime() > Date.now();
}
