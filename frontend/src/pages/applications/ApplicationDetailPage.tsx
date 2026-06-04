import { useEffect, useState } from "react";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface ApplicationDetail {
  id: string;
  candidate_id: string;
  cv_extraction_method: string | null;
  screening_score: number | null;
  screening_rationale: string | null;
  screening_status: string;
  status: string;
  interview_token: string | null;
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
  onBack: () => void;
  onInvite?: (id: string) => void;
}

export default function ApplicationDetailPage({ token, applicationId, onBack, onInvite }: Props) {
  const [app, setApp] = useState<ApplicationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BASE_URL}/applications/${applicationId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setApp)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [applicationId, token]);

  if (loading) return <div className="p-8 text-gray-500">Loading…</div>;
  if (!app) return <div className="p-8 text-red-600">{error ?? "Not found"}</div>;

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <div className="flex items-center gap-2 mb-6">
        <button onClick={onBack} className="text-gray-500 hover:text-gray-700 text-sm">
          ← Back
        </button>
        <h1 className="text-2xl font-bold text-gray-900">Application Detail</h1>
      </div>

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

      {app.screening_status === "qualified" && app.status === "qualified" && (
        <div className="mt-6">
          <button
            onClick={() => onInvite?.(app.id)}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            Send interview invitation
          </button>
        </div>
      )}
    </div>
  );
}
