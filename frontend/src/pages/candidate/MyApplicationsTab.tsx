import { useEffect, useState } from "react";
import { api, type CandidateApplication } from "../../services/api";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Spinner from "../../components/ui/Spinner";
import Badge from "../../components/ui/Badge";
import Modal from "../../components/ui/Modal";
import EmptyState from "../../components/ui/EmptyState";
import { statusColor } from "../../components/ui/status";
import { briefcaseIcon, interviewActive } from "./shared";

export default function MyApplicationsTab({ token }: { token: string }) {
  const [apps, setApps] = useState<CandidateApplication[] | null>(null);
  const [selected, setSelected] = useState<CandidateApplication | null>(null);

  useEffect(() => {
    void api.candidate.myApplications(token).then(setApps);
  }, [token]);

  if (!apps) return <Spinner label="Loading applications…" />;
  if (apps.length === 0)
    return (
      <EmptyState
        icon={briefcaseIcon}
        title="No applications yet"
        description="Roles you apply to — directly or by accepting an invitation — appear here."
      />
    );

  return (
    <>
      <ul className="space-y-3">
        {apps.map((a) => (
          <li key={a.id}>
            <Card interactive className="p-5" onClick={() => setSelected(a)}>
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <h3 className="font-semibold text-primary-900">{a.job_title ?? "Role"}</h3>
                  {a.company_name && (
                    <p className="mt-0.5 text-sm text-primary-500">{a.company_name}</p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {interviewActive(a) && <Badge status="invited">Interview ready</Badge>}
                  {a.feedback_token && <Badge status="evaluated">Feedback ready</Badge>}
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(
                      a.screening_status
                    )}`}
                  >
                    {a.screening_status === "pending" ? "Under review" : a.screening_status}
                  </span>
                </div>
              </div>
            </Card>
          </li>
        ))}
      </ul>

      <Modal
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected?.job_title ?? "Application"}
      >
        {selected && (
          <div className="space-y-4">
            {selected.company_name && (
              <p className="text-sm font-medium text-primary-500">{selected.company_name}</p>
            )}
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-primary-500">Screening:</span>
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(
                  selected.screening_status
                )}`}
              >
                {selected.screening_status === "pending" ? "Under review" : selected.screening_status}
              </span>
            </div>

            {interviewActive(selected) && (
              <div className="rounded-lg border border-brand-100 bg-brand-50/60 p-4">
                <p className="text-sm font-medium text-primary-800">You're invited to interview</p>
                <p className="mt-1 text-xs text-primary-500">
                  Complete your interview to move forward.
                </p>
                <a href={`/interview/${selected.interview_token}`}>
                  <Button size="sm" className="mt-3">
                    Start interview
                  </Button>
                </a>
              </div>
            )}

            {selected.feedback_token ? (
              <div className="rounded-lg border border-primary-100 bg-primary-50/60 p-4">
                <p className="text-sm font-medium text-primary-800">Interview feedback</p>
                {typeof selected.overall_score === "number" && (
                  <p className="mt-1 text-xs text-primary-500">
                    Overall score: {selected.overall_score}/100
                  </p>
                )}
                <a
                  href={`/feedback/${selected.feedback_token}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Button size="sm" variant="secondary" className="mt-3">
                    View feedback report
                  </Button>
                </a>
              </div>
            ) : (
              <p className="text-sm text-primary-500">
                Feedback will appear here once your interview has been evaluated.
              </p>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}
