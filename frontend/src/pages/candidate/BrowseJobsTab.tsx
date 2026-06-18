import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, type OpenJob } from "../../services/api";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Spinner from "../../components/ui/Spinner";
import Badge from "../../components/ui/Badge";
import Modal from "../../components/ui/Modal";
import EmptyState from "../../components/ui/EmptyState";
import { briefcaseIcon, type Notify } from "./shared";

export default function BrowseJobsTab({
  token,
  hasCv,
  onNotify,
}: {
  token: string;
  hasCv: boolean;
  onNotify: Notify;
}) {
  const [jobs, setJobs] = useState<OpenJob[] | null>(null);
  const [query, setQuery] = useState("");
  const [applying, setApplying] = useState<string | null>(null);
  const [selected, setSelected] = useState<OpenJob | null>(null);

  const load = useCallback(async () => {
    setJobs(await api.candidate.browseJobs(token));
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    if (!jobs) return null;
    const q = query.trim().toLowerCase();
    if (!q) return jobs;
    return jobs.filter((j) =>
      [j.title, j.company_name, j.description]
        .filter(Boolean)
        .some((v) => (v as string).toLowerCase().includes(q))
    );
  }, [jobs, query]);

  async function apply(jobId: string) {
    setApplying(jobId);
    try {
      await api.candidate.apply(token, jobId);
      onNotify({ kind: "ok", text: "Application submitted." });
      setSelected(null);
      await load();
    } catch (err) {
      onNotify({ kind: "err", text: err instanceof ApiError ? err.message : "Could not apply" });
    } finally {
      setApplying(null);
    }
  }

  if (!jobs) return <Spinner label="Loading open roles…" />;

  return (
    <div className="space-y-4">
      {!hasCv && (
        <div className="rounded-lg bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
          Upload a CV in <span className="font-medium">My CV &amp; profile</span> before you can apply.
        </div>
      )}

      <label className="relative block">
        <span className="sr-only">Search roles</span>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search roles by title, company, or keyword…"
          className="w-full rounded-lg border border-primary-200 bg-surface px-4 py-2.5 text-sm text-primary-800 placeholder:text-primary-400 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
        />
      </label>

      {filtered && filtered.length === 0 ? (
        <EmptyState
          icon={briefcaseIcon}
          title={query ? "No roles match your search" : "No open roles right now"}
          description={
            query ? "Try a different keyword." : "New roles will appear here as companies post them."
          }
        />
      ) : (
        <ul className="space-y-3">
          {filtered?.map((job) => (
            <li key={job.id}>
              <Card interactive className="p-5" onClick={() => setSelected(job)}>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-primary-900">{job.title}</h3>
                    {job.company_name && (
                      <p className="mt-0.5 text-sm text-primary-500">{job.company_name}</p>
                    )}
                    {job.description && (
                      <p className="mt-2 line-clamp-2 text-sm text-primary-600">{job.description}</p>
                    )}
                    <span className="mt-2 inline-block text-xs font-medium text-brand-600">
                      View details →
                    </span>
                  </div>
                  {job.already_applied && <Badge status="invited">Applied</Badge>}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}

      <Modal
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected?.title}
        footer={
          selected && (
            <>
              <Button variant="secondary" size="sm" onClick={() => setSelected(null)}>
                Close
              </Button>
              <Button
                size="sm"
                disabled={!hasCv || selected.already_applied}
                loading={applying === selected.id}
                onClick={() => apply(selected.id)}
              >
                {selected.already_applied ? "Already applied" : "Apply now"}
              </Button>
            </>
          )
        }
      >
        {selected && (
          <div>
            {selected.company_name && (
              <p className="text-sm font-medium text-primary-500">{selected.company_name}</p>
            )}
            <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-primary-700">
              {selected.description || "No description provided."}
            </p>
            {!hasCv && (
              <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                Upload a CV in your profile to apply.
              </p>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
