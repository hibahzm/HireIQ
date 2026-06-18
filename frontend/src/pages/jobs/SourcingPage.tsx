import { useEffect, useState } from "react";
import { api, ApiError, type SourcedCandidate } from "../../services/api";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Spinner from "../../components/ui/Spinner";
import { ArrowLeftIcon, UsersIcon } from "../../components/ui/icons";

interface Props {
  token: string;
  jobId: string;
  onBack: () => void;
}

function matchTone(score: number): string {
  if (score >= 0.66) return "bg-green-100 text-green-800";
  if (score >= 0.33) return "bg-amber-100 text-amber-800";
  return "bg-primary-100 text-primary-600";
}

export default function SourcingPage({ token, jobId, onBack }: Props) {
  const [candidates, setCandidates] = useState<SourcedCandidate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inviting, setInviting] = useState<string | null>(null);
  const [invited, setInvited] = useState<Set<string>>(new Set());

  useEffect(() => {
    api.sourcing
      .search(token, jobId)
      .then(setCandidates)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Search failed"));
  }, [token, jobId]);

  async function invite(candidateId: string) {
    setInviting(candidateId);
    try {
      await api.sourcing.invite(token, jobId, candidateId);
      setInvited((s) => new Set(s).add(candidateId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Invite failed");
    } finally {
      setInviting(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <button
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-primary-500 transition-colors hover:text-brand-700 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/50 rounded"
      >
        <ArrowLeftIcon className="h-4 w-4" /> Back to jobs
      </button>

      <header className="mt-3 mb-6">
        <h1 className="text-2xl font-bold text-primary-900">Sourced candidates</h1>
        <p className="mt-1 max-w-2xl text-sm text-primary-500">
          Ranked by how well each candidate's skills, experience, and overall CV fit this role.
          Only candidates open to work appear here — contact details unlock after they accept your
          invitation.
        </p>
      </header>

      {error && (
        <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      {!candidates && !error && (
        <div className="py-16">
          <Spinner label="Finding matching candidates…" />
        </div>
      )}

      {candidates && candidates.length === 0 && (
        <Card className="p-10 text-center">
          <UsersIcon className="mx-auto h-8 w-8 text-primary-300" />
          <p className="mt-3 text-sm font-medium text-primary-700">No matching candidates yet</p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-primary-500">
            No open-to-work candidates match this role right now. Check back as more job-seekers
            join and update their profiles.
          </p>
        </Card>
      )}

      {candidates && candidates.length > 0 && (
        <ul className="space-y-3">
          {candidates.map((c, i) => {
            const isInvited = invited.has(c.candidate_id);
            const pct = Math.round(c.match_score * 100);
            return (
              <li key={c.candidate_id}>
                <Card className="p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-50 text-sm font-semibold text-primary-500">
                        {i + 1}
                      </span>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-semibold text-primary-900">
                            {c.full_name ?? "Candidate"}
                          </h3>
                          <span
                            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${matchTone(
                              c.match_score
                            )}`}
                          >
                            {pct}% match
                          </span>
                          {c.already_applied && (
                            <span className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800">
                              Already applied
                            </span>
                          )}
                        </div>
                        <div className="mt-2 h-1.5 w-40 max-w-full overflow-hidden rounded-full bg-primary-100">
                          <div
                            className="h-full rounded-full bg-brand-500 transition-all"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    </div>

                    <Button
                      size="sm"
                      disabled={c.already_applied || isInvited}
                      loading={inviting === c.candidate_id}
                      onClick={() => invite(c.candidate_id)}
                      className="shrink-0"
                    >
                      {c.already_applied ? "Applied" : isInvited ? "Invited" : "Invite"}
                    </Button>
                  </div>

                  {(c.matched_skills.length > 0 || c.missing_skills.length > 0) && (
                    <div className="mt-4 flex flex-wrap gap-1.5 pl-11">
                      {c.matched_skills.map((m) => (
                        <span
                          key={m.skill}
                          className="inline-flex items-center gap-1 rounded-md bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700 ring-1 ring-green-100"
                        >
                          {m.skill}
                          {m.years != null && (
                            <span className="text-green-500">· {m.years}y</span>
                          )}
                        </span>
                      ))}
                      {c.missing_skills.map((s) => (
                        <span
                          key={s}
                          className="inline-flex items-center rounded-md bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary-400 line-through ring-1 ring-primary-100"
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  )}
                </Card>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
