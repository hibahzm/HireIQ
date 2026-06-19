import { useState } from "react";
import { api, ApiError, type SourcingInviteResult } from "../../services/api";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import { ArrowLeftIcon, UsersIcon } from "../../components/ui/icons";

interface Props {
  token: string;
  jobId: string;
  onBack: () => void;
}

export default function SourcingPage({ token, jobId, onBack }: Props) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SourcingInviteResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function findAndInvite() {
    setRunning(true);
    setError(null);
    try {
      setResult(await api.sourcing.inviteMatches(token, jobId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Sourcing failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <button
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-primary-500 transition-colors hover:text-brand-700 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/50 rounded"
      >
        <ArrowLeftIcon className="h-4 w-4" /> Back to jobs
      </button>

      <header className="mt-3 mb-6">
        <h1 className="text-2xl font-bold text-primary-900">Source candidates</h1>
        <p className="mt-1 text-sm text-primary-500">
          We find strong matches for this role among open-to-work candidates and invite them
          directly. Candidates decide whether to apply — you'll see full details and screening only
          once someone applies.
        </p>
      </header>

      <Card className="p-6">
        <div className="flex items-start gap-4">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-600">
            <UsersIcon className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h2 className="font-semibold text-primary-900">Find &amp; invite matching candidates</h2>
            <p className="mt-1 text-sm text-primary-500">
              Only strong matches are invited, and anyone already invited or applied is skipped —
              so it's safe to run again as new candidates join.
            </p>
            <Button className="mt-4" loading={running} onClick={findAndInvite}>
              {result ? "Run again" : "Find & invite candidates"}
            </Button>
          </div>
        </div>
      </Card>

      {error && (
        <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      {result && !error && (
        <div
          className="mt-4 rounded-lg bg-green-50 px-4 py-3 text-sm text-green-800"
          role="status"
        >
          {result.invited > 0 ? (
            <>
              Invited <span className="font-semibold">{result.invited}</span>{" "}
              {result.invited === 1 ? "candidate" : "candidates"}.
            </>
          ) : (
            <>No new candidates to invite right now.</>
          )}
          {result.skipped > 0 && (
            <> {result.skipped} already invited or applied.</>
          )}
        </div>
      )}
    </div>
  );
}
