import { useEffect, useState } from "react";
import { api, ApiError, type SourcedCandidate } from "../../services/api";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Spinner from "../../components/ui/Spinner";

interface Props {
  token: string;
  jobId: string;
  onBack: () => void;
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
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <button onClick={onBack} className="text-sm text-primary-500 hover:text-brand-700">
            ← Back to jobs
          </button>
          <h1 className="mt-1 text-xl font-bold text-primary-900">Sourced candidates</h1>
          <p className="text-sm text-primary-500">
            Ranked by skill &amp; years match. Candidates are only shown if they are open to work;
            contact details are revealed after they accept your invitation.
          </p>
        </div>
      </div>

      {error && (
        <p className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      {!candidates && !error && <Spinner />}
      {candidates && candidates.length === 0 && (
        <p className="text-sm text-primary-500">
          No matching open-to-work candidates yet.
        </p>
      )}

      {candidates?.map((c) => {
        const isInvited = invited.has(c.candidate_id);
        return (
          <Card key={c.candidate_id} className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-primary-900">{c.full_name ?? "Candidate"}</h3>
                <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">
                  {Math.round(c.match_score * 100)}% match
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {c.matched_skills.map((m) => (
                  <span
                    key={m.skill}
                    className="rounded-md bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700"
                  >
                    {m.skill}
                    {m.years != null ? ` · ${m.years}y` : ""}
                  </span>
                ))}
                {c.missing_skills.map((s) => (
                  <span key={s} className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                    missing: {s}
                  </span>
                ))}
              </div>
            </div>
            <Button
              size="sm"
              disabled={c.already_applied || isInvited}
              loading={inviting === c.candidate_id}
              onClick={() => invite(c.candidate_id)}
            >
              {c.already_applied ? "Applied" : isInvited ? "Invited" : "Invite"}
            </Button>
          </Card>
        );
      })}
    </div>
  );
}
