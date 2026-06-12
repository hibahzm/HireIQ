import { useEffect, useState } from "react";
import { api, Job, ApiError } from "../../services/api";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
import PageHeader from "../../components/ui/PageHeader";
import EmptyState from "../../components/ui/EmptyState";
import Spinner from "../../components/ui/Spinner";
import { BriefcaseIcon, CopyIcon, PlusIcon } from "../../components/ui/icons";
import { useAuth } from "../../context/AuthContext";

interface Props {
  token: string;
  onSelectJob: (id: string) => void;
  onSetupJob: (id: string) => void;
}

export default function JobListPage({ token, onSelectJob, onSetupJob }: Props) {
  const { user } = useAuth();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [useRealtimeInterview, setUseRealtimeInterview] = useState(true);
  const [creating, setCreating] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [actingId, setActingId] = useState<string | null>(null);
  const isAdmin = user?.role === "admin";

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
    setError(null);
    try {
      const job = await api.jobs.create(token, {
        title: newTitle.trim(),
        description: newDescription.trim() || undefined,
        streaming_interview: useRealtimeInterview,
      });
      // Continue straight into AI-guided setup, where the agent reads the
      // description and only asks about whatever is missing.
      onSetupJob(job.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create job");
      setCreating(false);
    }
  }

  function copyApplyLink(jobId: string) {
    const link = `${window.location.origin}/apply/${jobId}`;
    navigator.clipboard?.writeText(link);
    setCopiedId(jobId);
    setTimeout(() => setCopiedId((c) => (c === jobId ? null : c)), 1500);
  }

  function jobActionError(err: unknown, fallback: string) {
    if (!(err instanceof ApiError)) return fallback;
    if (err.message === "criteria_not_set") {
      return "Complete setup or save criteria before activating this job.";
    }
    if (err.message.startsWith("cannot_transition_from_")) {
      return "This job cannot move to that status from its current state.";
    }
    return err.message;
  }

  async function runJobAction(jobId: string, action: () => Promise<Job>, message: string) {
    setActingId(jobId);
    setError(null);
    try {
      const updated = await action();
      setJobs((prev) => prev.map((job) => (job.id === jobId ? updated : job)));
    } catch (err) {
      setError(jobActionError(err, message));
    } finally {
      setActingId(null);
    }
  }

  async function handleDelete(job: Job) {
    if (!confirm(`Delete "${job.title}"? This only works before applications exist.`)) return;
    setActingId(job.id);
    setError(null);
    try {
      await api.jobs.delete(token, job.id);
      setJobs((prev) => prev.filter((j) => j.id !== job.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete job");
    } finally {
      setActingId(null);
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner label="Loading jobs…" />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Jobs"
        description="Create roles, run AI-guided setup, and share the public application link."
        actions={
          !showForm && (
            <Button onClick={() => setShowForm(true)}>
              <PlusIcon /> New job
            </Button>
          )
        }
      />

      {error && (
        <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      {showForm && (
        <Card className="mb-6 p-5">
          <h2 className="mb-1 text-base font-semibold text-primary-800">Create a new job</h2>
          <p className="mb-4 text-sm text-primary-500">
            Add the title and a project / job description. The setup assistant will read the
            description, extract criteria automatically, and only ask about anything missing.
          </p>
          <form onSubmit={handleCreate} className="space-y-4">
            <div>
              <label htmlFor="job-title" className="block text-sm font-medium text-primary-700">
                Job title
              </label>
              <input
                id="job-title"
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="e.g. Senior Backend Engineer"
                required
                className="mt-1 block w-full rounded-lg border border-primary-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
              />
            </div>
            <div>
              <label htmlFor="job-desc" className="block text-sm font-medium text-primary-700">
                Project / job description
                <span className="ml-1 font-normal text-primary-400">(recommended)</span>
              </label>
              <textarea
                id="job-desc"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                rows={6}
                placeholder="Describe the role, responsibilities, required skills, experience level, must-haves and dealbreakers. The more detail you give, the fewer questions the assistant will ask."
                className="mt-1 block w-full rounded-lg border border-primary-200 px-3 py-2.5 text-sm leading-relaxed focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
              />
            </div>
            <label className="flex items-center gap-3 rounded-lg border border-primary-200 px-3 py-2.5 text-sm text-primary-700">
              <input
                type="checkbox"
                checked={useRealtimeInterview}
                onChange={(e) => setUseRealtimeInterview(e.target.checked)}
                className="h-4 w-4 rounded border-primary-300 text-brand-600 focus:ring-brand-500"
              />
              <span>Realtime voice interview</span>
            </label>
            <div className="flex gap-2">
              <Button type="submit" loading={creating} disabled={!newTitle.trim()}>
                Create &amp; start setup
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setShowForm(false);
                  setNewTitle("");
                  setNewDescription("");
                  setUseRealtimeInterview(true);
                }}
              >
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      {jobs.length === 0 ? (
        <EmptyState
          icon={<BriefcaseIcon className="h-8 w-8" />}
          title="No jobs yet"
          description="Create your first job to start receiving and screening applications."
          action={
            !showForm && (
              <Button onClick={() => setShowForm(true)}>
                <PlusIcon /> New job
              </Button>
            )
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-primary-100 bg-primary-50/50 text-left text-xs uppercase tracking-wide text-primary-400">
                <th className="px-5 py-3 font-semibold">Title</th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3 font-semibold">Interview</th>
                <th className="px-5 py-3 font-semibold">Created</th>
                <th className="px-5 py-3 font-semibold">Apply link</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-primary-100">
              {jobs.map((job) => (
                <tr key={job.id} className="transition-colors hover:bg-primary-50/60">
                  <td className="px-5 py-3">
                    <button
                      onClick={() => onSelectJob(job.id)}
                      className="font-semibold text-brand-700 hover:underline cursor-pointer"
                    >
                      {job.title}
                    </button>
                  </td>
                  <td className="px-5 py-3">
                    <Badge status={job.status} />
                  </td>
                  <td className="px-5 py-3 text-primary-500">
                    {job.streaming_interview ? "Realtime" : "Recorded"}
                  </td>
                  <td className="px-5 py-3 text-primary-500">
                    {new Date(job.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-5 py-3">
                    <button
                      onClick={() => copyApplyLink(job.id)}
                      className="inline-flex items-center gap-1.5 text-xs font-medium text-primary-500 hover:text-brand-700 cursor-pointer"
                      aria-label={`Copy public application link for ${job.title}`}
                    >
                      <CopyIcon className="h-4 w-4" />
                      {copiedId === job.id ? "Copied!" : "Copy link"}
                    </button>
                  </td>
                  <td className="px-5 py-3 text-right">
                    <div className="inline-flex flex-wrap justify-end gap-2">
                      {(job.status === "draft" ||
                        job.status === "setup" ||
                        job.status === "setup_failed") && (
                        <Button size="sm" variant="secondary" onClick={() => onSetupJob(job.id)}>
                          Setup
                        </Button>
                      )}
                      {(job.status === "setup" || job.status === "setup_failed") && (
                        <Button
                          size="sm"
                          className="bg-green-600 hover:bg-green-700"
                          loading={actingId === job.id}
                          onClick={() =>
                            runJobAction(
                              job.id,
                              () => api.jobs.activate(token, job.id),
                              "Failed to activate job",
                            )
                          }
                        >
                          Activate
                        </Button>
                      )}
                      {job.status === "active" && (
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={actingId === job.id}
                          onClick={() =>
                            runJobAction(
                              job.id,
                              () => api.jobs.close(token, job.id),
                              "Failed to close job",
                            )
                          }
                        >
                          Close
                        </Button>
                      )}
                      {(job.status === "closed" || job.status === "archived") && (
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={actingId === job.id}
                          onClick={() =>
                            runJobAction(
                              job.id,
                              () => api.jobs.reopen(token, job.id),
                              "Failed to reopen job",
                            )
                          }
                        >
                          {job.status === "archived" ? "Restore" : "Reopen"}
                        </Button>
                      )}
                      {job.status !== "archived" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          loading={actingId === job.id}
                          onClick={() =>
                            runJobAction(
                              job.id,
                              () => api.jobs.archive(token, job.id),
                              "Failed to archive job",
                            )
                          }
                        >
                          Archive
                        </Button>
                      )}
                      {isAdmin && ["draft", "setup", "setup_failed", "archived"].includes(job.status) && (
                        <Button
                          size="sm"
                          variant="danger"
                          loading={actingId === job.id}
                          onClick={() => handleDelete(job)}
                        >
                          Delete
                        </Button>
                      )}
                    </div>
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
