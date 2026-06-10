import { useEffect, useState } from "react";
import { api, Application, ApiError } from "../../services/api";
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
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const applyLink = `${window.location.origin}/apply/${jobId}`;

  useEffect(() => {
    api.applications
      .listByJob(token, jobId)
      .then(setApplications)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load applications"))
      .finally(() => setLoading(false));
  }, [jobId, token]);

  async function handleInvite(applicationId: string) {
    try {
      await api.applications.invite(token, applicationId);
      setApplications((prev) =>
        prev.map((a) => (a.id === applicationId ? { ...a, status: "invited" } : a))
      );
    } catch {
      setError("Failed to send invite");
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

      <Card className="mb-6 p-4">
        <p className="mb-2 text-sm font-medium text-primary-700">
          Public application link
        </p>
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
                  </td>
                  <td className="px-5 py-3">
                    <Badge status={app.status} />
                  </td>
                  <td className="px-5 py-3 text-primary-500">
                    {new Date(app.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-5 py-3 text-right">
                    {app.screening_status === "qualified" && app.status === "qualified" && (
                      <Button size="sm" variant="secondary" onClick={() => handleInvite(app.id)}>
                        Invite
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
