import { useEffect, useState } from "react";
import { api, Job, ApiError } from "../../services/api";

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-100 text-gray-700",
  setup: "bg-yellow-100 text-yellow-800",
  active: "bg-green-100 text-green-800",
  paused: "bg-orange-100 text-orange-800",
  closed: "bg-red-100 text-red-700",
};

interface Props {
  token: string;
  onSelectJob: (id: string) => void;
  onSetupJob: (id: string) => void;
}

export default function JobListPage({ token, onSelectJob, onSetupJob }: Props) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api.jobs
      .list(token)
      .then(setJobs)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setCreating(true);
    try {
      const job = await api.jobs.create(token, { title: newTitle.trim() });
      setJobs((prev) => [job, ...prev]);
      setNewTitle("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create job");
    } finally {
      setCreating(false);
    }
  }

  if (loading) return <div className="p-8 text-gray-500">Loading jobs…</div>;

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Jobs</h1>

      <form onSubmit={handleCreate} className="flex gap-2 mb-6">
        <input
          type="text"
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="New job title"
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          type="submit"
          disabled={creating}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {creating ? "Creating…" : "New job"}
        </button>
      </form>

      {error && <p className="text-red-600 mb-4" role="alert">{error}</p>}

      {jobs.length === 0 ? (
        <p className="text-gray-500">No jobs yet. Create your first job above.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              <th className="text-left py-2 font-medium text-gray-700">Title</th>
              <th className="text-left py-2 font-medium text-gray-700">Status</th>
              <th className="text-left py-2 font-medium text-gray-700">Created</th>
              <th className="py-2"></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id} className="border-b hover:bg-gray-50">
                <td className="py-2">
                  <button
                    onClick={() => onSelectJob(job.id)}
                    className="text-blue-600 hover:underline font-medium"
                  >
                    {job.title}
                  </button>
                </td>
                <td className="py-2">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[job.status] ?? ""}`}>
                    {job.status}
                  </span>
                </td>
                <td className="py-2 text-gray-500">
                  {new Date(job.created_at).toLocaleDateString()}
                </td>
                <td className="py-2 text-right">
                  {(job.status === "draft" || job.status === "setup") && (
                    <button
                      onClick={() => onSetupJob(job.id)}
                      className="text-sm text-blue-600 hover:underline"
                    >
                      Setup
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
