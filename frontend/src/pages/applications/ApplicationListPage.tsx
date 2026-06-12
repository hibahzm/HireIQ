import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Application, Job, ApiError } from "../../services/api";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
import PageHeader from "../../components/ui/PageHeader";
import Spinner from "../../components/ui/Spinner";
import { CopyIcon, ExternalLinkIcon } from "../../components/ui/icons";

interface Props {
  token: string;
  jobId: string;
  onSelectApplication: (id: string) => void;
  onBack: () => void;
}

export default function ApplicationListPage({ token, jobId, onSelectApplication }: Props) {
  const navigate = useNavigate();
  const [applications, setApplications] = useState<Application[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [copiedInviteId, setCopiedInviteId] = useState<string | null>(null);
  const [rescreening, setRescreening] = useState<string | null>(null);

  const applyLink = `${window.location.origin}/apply/${jobId}`;
  const isActive = job?.status === "active";

  useEffect(() => {
    Promise.all([
      api.applications.listByJob(token, jobId).then(setApplications),
      api.jobs.get(token, jobId).then(setJob).catch(() => {}),
    ])
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load applications"))
      .finally(() => setLoading(false));
  }, [jobId, token]);

  async function handleInvite(applicationId: string) {
    try {
      const invite = await api.applications.invite(token, applicationId);
      setApplications((prev) =>
        prev.map((a) =>
          a.id === applicationId
            ? {
                ...a,
                status: "invited",
                interview_token: invite.interview_token,
                interview_token_expires_at: invite.expires_at,
              }
            : a
        )
      );
    } catch {
      setError("Failed to send invite");
    }
  }

  function interviewLink(app: Application) {
    return app.interview_token ? `${window.location.origin}/interview/${app.interview_token}` : "";
  }

  function copyInterviewLink(app: Application) {
    const link = interviewLink(app);
    if (!link) return;
    navigator.clipboard?.writeText(link);
    setCopiedInviteId(app.id);
    setTimeout(() => setCopiedInviteId((id) => (id === app.id ? null : id)), 1500);
  }

  async function handleRescreen(applicationId: string) {
    setRescreening(applicationId);
    setError(null);
    try {
      await api.applications.rescreen(token, applicationId);
      setApplications((prev) =>
        prev.map((a) =>
          a.id === applicationId
            ? { ...a, screening_status: "pending", screening_score: null, screening_rationale: null }
            : a
        )
      );
    } catch {
      setError("Failed to re-run screening");
    } finally {
      setRescreening(null);
    }
  }

  function copyLink() {
    navigator.clipboard?.writeText(applyLink);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner label="Loading applications…" />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Applications"
        description="Candidates who applied via the public link. Qualified candidates can be invited to interview."
      />

      {job && !isActive && (
        <div className="mb-6 flex flex-col gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-2">
            <Badge status={job.status} />
            <p className="text-sm text-amber-800">
              This job isn't <strong>active</strong> yet, so candidates can't apply — submissions
              will be rejected. Finish AI setup and activate the job to start accepting applications.
            </p>
          </div>
          <Button
            size="sm"
            onClick={() => navigate(`/jobs/${jobId}/setup`)}
            className="shrink-0 bg-amber-600 hover:bg-amber-700"
          >
            Finish setup &amp; activate
          </Button>
        </div>
      )}

      <Card className="mb-6 p-4">
        <div className="mb-2 flex items-center gap-2">
          <p className="text-sm font-medium text-primary-700">Public application link</p>
          {isActive && <Badge status="active" />}
        </div>
        <p className="mb-3 text-xs text-primary-500">
          Share this with candidates — anyone with the link can submit their name, email and CV.
        </p>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <code className="flex-1 overflow-x-auto rounded-lg border border-primary-200 bg-primary-50 px-3 py-2 text-xs text-primary-700">
            {applyLink}
          </code>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={copyLink}>
              <CopyIcon className="h-4 w-4" /> {copied ? "Copied!" : "Copy"}
            </Button>
            <a href={`/apply/${jobId}`} target="_blank" rel="noopener noreferrer">
              <Button size="sm" variant="ghost">
                <ExternalLinkIcon className="h-4 w-4" /> Open
              </Button>
            </a>
          </div>
        </div>
      </Card>

      {error && (
        <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      {applications.length === 0 ? (
        <p className="text-sm text-primary-500">No applications yet.</p>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-primary-100 bg-primary-50/50 text-left text-xs uppercase tracking-wide text-primary-400">
                <th className="px-5 py-3 font-semibold">Application</th>
                <th className="px-5 py-3 font-semibold">Score</th>
                <th className="px-5 py-3 font-semibold">Screening</th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3 font-semibold">Applied</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-primary-100">
              {applications.map((app) => (
                <tr key={app.id} className="transition-colors hover:bg-primary-50/60">
                  <td className="px-5 py-3">
                    <button
                      onClick={() => onSelectApplication(app.id)}
                      className="font-mono text-xs font-semibold text-brand-700 hover:underline cursor-pointer"
                    >
                      {app.id.slice(0, 8)}…
                    </button>
                  </td>
                  <td className="px-5 py-3">
                    {app.screening_score !== null ? (
                      <span className="font-semibold text-primary-800">{app.screening_score}</span>
                    ) : (
                      <span className="text-primary-300">—</span>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <Badge status={app.screening_status} />
                    {app.screening_status === "failed" && app.screening_rationale && (
                      <p className="mt-1 max-w-xs text-xs leading-snug text-red-600">
                        {app.screening_rationale}
                      </p>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <Badge status={app.status} />
                  </td>
                  <td className="px-5 py-3 text-primary-500">
                    {new Date(app.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-5 py-3 text-right">
                    {app.status === "invited" && app.interview_token && (
                      <div className="inline-flex gap-2">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => copyInterviewLink(app)}
                        >
                          <CopyIcon className="h-4 w-4" />{" "}
                          {copiedInviteId === app.id ? "Copied!" : "Copy interview"}
                        </Button>
                        <a href={interviewLink(app)} target="_blank" rel="noopener noreferrer">
                          <Button size="sm" variant="ghost">
                            <ExternalLinkIcon className="h-4 w-4" /> Open
                          </Button>
                        </a>
                      </div>
                    )}
                    {app.evaluation_id && (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => navigate(`/evaluations/${app.evaluation_id}`)}
                      >
                        View evaluation
                      </Button>
                    )}
                    {app.screening_status === "qualified" && app.status === "qualified" && (
                      <Button size="sm" variant="secondary" onClick={() => handleInvite(app.id)}>
                        Invite
                      </Button>
                    )}
                    {(app.screening_status === "pending" ||
                      app.screening_status === "failed") && (
                      <Button
                        size="sm"
                        variant="secondary"
                        loading={rescreening === app.id}
                        onClick={() => handleRescreen(app.id)}
                      >
                        Re-run screening
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
