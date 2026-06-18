import { useCallback, useEffect, useState } from "react";
import {
  api,
  ApiError,
  type CandidateApplication,
  type Invitation,
} from "../../services/api";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Spinner from "../../components/ui/Spinner";
import EmptyState from "../../components/ui/EmptyState";
import { briefcaseIcon, interviewActive, type Notify } from "./shared";

export default function InvitationsTab({ token, onNotify }: { token: string; onNotify: Notify }) {
  const [invites, setInvites] = useState<Invitation[] | null>(null);
  const [apps, setApps] = useState<CandidateApplication[] | null>(null);
  const [accepting, setAccepting] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [inv, ap] = await Promise.all([
      api.candidate.invitations(token),
      api.candidate.myApplications(token),
    ]);
    setInvites(inv);
    setApps(ap);
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function accept(id: string) {
    setAccepting(id);
    try {
      await api.candidate.acceptInvitation(token, id);
      onNotify({ kind: "ok", text: "Invitation accepted — your application was submitted." });
      await load();
    } catch (err) {
      onNotify({ kind: "err", text: err instanceof ApiError ? err.message : "Could not accept" });
    } finally {
      setAccepting(null);
    }
  }

  if (!invites || !apps) return <Spinner label="Loading invitations…" />;

  const pendingSourcing = invites.filter((i) => i.status === "pending");
  const interviewReady = apps.filter(interviewActive);

  if (pendingSourcing.length === 0 && interviewReady.length === 0)
    return (
      <EmptyState
        icon={briefcaseIcon}
        title="No invitations yet"
        description="When a company invites you to apply, or you're invited to interview after applying, it shows up here."
      />
    );

  return (
    <div className="space-y-6">
      {interviewReady.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold text-primary-700">Interview invitations</h2>
          <ul className="space-y-3">
            {interviewReady.map((a) => (
              <li key={a.id}>
                <Card className="flex items-center justify-between gap-4 p-5">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-primary-900">{a.job_title ?? "Role"}</h3>
                    {a.company_name && (
                      <p className="mt-0.5 text-sm text-primary-500">{a.company_name}</p>
                    )}
                    <p className="mt-1 text-xs text-primary-400">
                      You're qualified — complete your interview.
                    </p>
                  </div>
                  <a href={`/interview/${a.interview_token}`}>
                    <Button size="sm" className="shrink-0">
                      Start interview
                    </Button>
                  </a>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}

      {pendingSourcing.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold text-primary-700">Job invitations</h2>
          <ul className="space-y-3">
            {pendingSourcing.map((inv) => (
              <li key={inv.id}>
                <Card className="flex items-start justify-between gap-4 p-5">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-primary-900">{inv.job_title ?? "Role"}</h3>
                    {inv.company_name && (
                      <p className="mt-0.5 text-sm text-primary-500">{inv.company_name}</p>
                    )}
                    {inv.message && <p className="mt-2 text-sm text-primary-600">{inv.message}</p>}
                  </div>
                  <Button
                    size="sm"
                    loading={accepting === inv.id}
                    onClick={() => accept(inv.id)}
                    className="shrink-0"
                  >
                    Accept &amp; apply
                  </Button>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
