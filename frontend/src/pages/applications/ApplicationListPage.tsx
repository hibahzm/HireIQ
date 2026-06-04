import { useEffect, useState } from "react";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface Application {
  id: string;
  candidate_id: string;
  screening_score: number | null;
  screening_status: string;
  status: string;
  created_at: string;
}

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  qualified: "Qualified",
  rejected: "Rejected",
  screening: "Screening",
  system_interrupted: "Interrupted",
  abandoned: "Abandoned",
  invited: "Invited",
  interviewing: "Interviewing",
  evaluated: "Evaluated",
};

const STATUS_COLORS: Record<string, string> = {
  qualified: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-700",
  pending: "bg-gray-100 text-gray-700",
  screening: "bg-yellow-100 text-yellow-800",
  system_interrupted: "bg-orange-100 text-orange-800",
  abandoned: "bg-gray-100 text-gray-500",
  invited: "bg-blue-100 text-blue-800",
  interviewing: "bg-purple-100 text-purple-800",
  evaluated: "bg-indigo-100 text-indigo-800",
};

interface Props {
  token: string;
  jobId: string;
  onSelectApplication: (id: string) => void;
  onBack: () => void;
}

export default function ApplicationListPage({ token, jobId, onSelectApplication, onBack }: Props) {
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BASE_URL}/jobs/${jobId}/applications`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setApplications)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [jobId, token]);

  async function handleInvite(applicationId: string) {
    try {
      await fetch(`${BASE_URL}/applications/${applicationId}/invite`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      setApplications((prev) =>
        prev.map((a) => (a.id === applicationId ? { ...a, status: "invited" } : a))
      );
    } catch {
      setError("Failed to send invite");
    }
  }

  if (loading) return <div className="p-8 text-gray-500">Loading applications…</div>;

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center gap-2 mb-6">
        <button onClick={onBack} className="text-gray-500 hover:text-gray-700 text-sm">
          ← Back to jobs
        </button>
        <h1 className="text-2xl font-bold text-gray-900">Applications</h1>
      </div>

      {error && <p className="text-red-600 mb-4" role="alert">{error}</p>}

      {applications.length === 0 ? (
        <p className="text-gray-500">No applications yet.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              <th className="text-left py-2 font-medium text-gray-700">ID</th>
              <th className="text-left py-2 font-medium text-gray-700">Score</th>
              <th className="text-left py-2 font-medium text-gray-700">Screening</th>
              <th className="text-left py-2 font-medium text-gray-700">Status</th>
              <th className="text-left py-2 font-medium text-gray-700">Applied</th>
              <th className="py-2"></th>
            </tr>
          </thead>
          <tbody>
            {applications.map((app) => (
              <tr key={app.id} className="border-b hover:bg-gray-50">
                <td className="py-2">
                  <button
                    onClick={() => onSelectApplication(app.id)}
                    className="text-blue-600 hover:underline font-mono text-xs"
                  >
                    {app.id.slice(0, 8)}…
                  </button>
                </td>
                <td className="py-2">
                  {app.screening_score !== null ? (
                    <span className="font-semibold">{app.screening_score}</span>
                  ) : (
                    <span className="text-gray-400">—</span>
                  )}
                </td>
                <td className="py-2">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[app.screening_status] ?? "bg-gray-100"}`}>
                    {STATUS_LABELS[app.screening_status] ?? app.screening_status}
                  </span>
                </td>
                <td className="py-2">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[app.status] ?? "bg-gray-100"}`}>
                    {STATUS_LABELS[app.status] ?? app.status}
                  </span>
                </td>
                <td className="py-2 text-gray-500">
                  {new Date(app.created_at).toLocaleDateString()}
                </td>
                <td className="py-2 text-right">
                  {app.screening_status === "qualified" && app.status === "qualified" && (
                    <button
                      onClick={() => handleInvite(app.id)}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      Invite
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
