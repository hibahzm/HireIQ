import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../services/api";
import Button from "../../components/ui/Button";
import { CopyIcon, ExternalLinkIcon } from "../../components/ui/icons";

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api";

interface ApplicationDetail {
  id: string;
  job_id: string;
  candidate_id: string;
  cv_extraction_method: string | null;
  screening_score: number | null;
  screening_rationale: string | null;
  screening_status: string;
  status: string;
  interview_token: string | null;
  evaluation_id: string | null;
  created_at: string;
  updated_at: string;
}

const STATUS_COLORS: Record<string, string> = {
  qualified: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-700",
  pending: "bg-gray-100 text-gray-700",
  screening: "bg-yellow-100 text-yellow-800",
  system_interrupted: "bg-orange-100 text-orange-800",
  abandoned: "bg-gray-100 text-gray-500",
};

interface Props {
  token: string;
  applicationId: string;
  onBack?: () => void;
  onInvite?: (id: string) => void;
}

export default function ApplicationDetailPage({ token, applicationId, onInvite }: Props) {
  const navigate = useNavigate();
  const [app, setApp] = useState<ApplicationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  const [copiedInvite, setCopiedInvite] = useState(false);

  useEffect(() => {
    fetch(`${BASE_URL}/applications/${applicationId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => null);
          throw new Error(body?.detail ?? `Failed to load application (${r.status})`);
        }
        return r.json();
      })
      .then(setApp)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [applicationId, token]);

  async function handleInvite() {
    if (!app) return;
    setInviting(true);
    setError(null);
    try {
      const invite = await api.applications.invite(token, app.id);
      setApp({
        ...app,
        status: "invited",
        interview_token: invite.interview_token,
      });
      onInvite?.(app.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to send invitation");
    } finally {
      setInviting(false);
    }
  }

  const interviewLink =
    app?.interview_token ? `${window.location.origin}/interview/${app.interview_token}` : "";

  function copyInterviewLink() {
    if (!interviewLink) return;
    navigator.clipboard?.writeText(interviewLink);
    setCopiedInvite(true);
    setTimeout(() => setCopiedInvite(false), 1500);
  }

  if (loading) return <div className="text-primary-500">Loading…</div>;
  if (!app) return <div className="text-red-600">{error ?? "Not found"}</div>;

  return (
    <div className="max-w-2xl">
      <h1 className="mb-6 text-2xl font-bold tracking-tight text-primary-800">Application detail</h1>

      <dl className="space-y-4">
        <div>
          <dt className="text-sm font-medium text-gray-500">Application ID</dt>
          <dd className="text-sm font-mono text-gray-900">{app.id}</dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-gray-500">CV extraction method</dt>
          <dd className="text-sm text-gray-900">{app.cv_extraction_method ?? "Not yet extracted"}</dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-gray-500">Screening score</dt>
          <dd className="text-2xl font-bold text-gray-900">
            {app.screening_score !== null ? `${app.screening_score}/100` : "Pending"}
          </dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-gray-500">Screening status</dt>
          <dd>
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[app.screening_status] ?? "bg-gray-100"}`}>
              {app.screening_status}
            </span>
          </dd>
        </div>
        {app.screening_rationale && (
          <div>
            <dt className="text-sm font-medium text-gray-500">Rationale</dt>
            <dd className="text-sm text-gray-900 mt-1 p-3 bg-gray-50 rounded-md">
              {app.screening_rationale}
            </dd>
          </div>
        )}
        <div>
          <dt className="text-sm font-medium text-gray-500">Application status</dt>
          <dd>
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[app.status] ?? "bg-gray-100"}`}>
              {app.status}
            </span>
            {app.status === "system_interrupted" && (
              <span className="ml-2 text-xs text-orange-600">
                Session interrupted — candidate can resume
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-gray-500">Applied</dt>
          <dd className="text-sm text-gray-900">
            {new Date(app.created_at).toLocaleString()}
          </dd>
        </div>
      </dl>

      {error && <p className="mt-4 text-sm text-red-600" role="alert">{error}</p>}

      {app.evaluation_id && (
        <div className="mt-6">
          <Button
            variant="secondary"
            onClick={() => navigate(`/evaluations/${app.evaluation_id}`)}
          >
            View interview evaluation
          </Button>
        </div>
      )}

      {app.status === "invited" ? (
        <div className="mt-6 rounded-lg border border-green-200 bg-green-50 p-4">
          <p className="mb-3 text-sm font-medium text-green-800">Interview invitation sent.</p>
          {interviewLink && (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <code className="flex-1 overflow-x-auto rounded-md border border-green-200 bg-white px-3 py-2 text-xs text-green-800">
                {interviewLink}
              </code>
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" onClick={copyInterviewLink}>
                  <CopyIcon className="h-4 w-4" /> {copiedInvite ? "Copied!" : "Copy"}
                </Button>
                <a href={interviewLink} target="_blank" rel="noopener noreferrer">
                  <Button size="sm" variant="ghost">
                    <ExternalLinkIcon className="h-4 w-4" /> Open
                  </Button>
                </a>
              </div>
            </div>
          )}
        </div>
      ) : (
        app.screening_status === "qualified" &&
        app.status === "qualified" && (
          <div className="mt-6">
            <button
              onClick={handleInvite}
              disabled={inviting}
              className="rounded-lg bg-brand-600 px-4 py-2.5 font-semibold text-white transition-colors hover:bg-brand-700 disabled:opacity-60 cursor-pointer"
            >
              {inviting ? "Sending…" : "Send interview invitation"}
            </button>
          </div>
        )
      )}
    </div>
  );
}
