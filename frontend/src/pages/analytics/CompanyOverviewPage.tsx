import { useEffect, useState } from "react";
import { api, ApiError, type CompanyOverview } from "../../services/api";

interface Props {
  token: string;
  onSelectJob: (jobId: string) => void;
  onViewJobAnalytics: (jobId: string) => void;
}

const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);
const num = (v: number | null) => (v === null ? "—" : String(v));

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="text-sm text-gray-600">{label}</div>
      <div className="mt-1 text-3xl font-semibold text-gray-900">{value}</div>
    </div>
  );
}

export default function CompanyOverviewPage({ token, onSelectJob, onViewJobAnalytics }: Props) {
  const [data, setData] = useState<CompanyOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api.analytics
      .overview(token)
      .then((d) => active && setData(d))
      .catch((e) =>
        active && setError(e instanceof ApiError ? e.message : "Failed to load overview")
      );
    return () => {
      active = false;
    };
  }, [token]);

  if (error) {
    return <div className="min-h-screen bg-gray-50 p-8 text-red-600" role="alert">{error}</div>;
  }
  if (!data) {
    return <div className="min-h-screen bg-gray-50 p-8 text-gray-600">Loading overview…</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-5xl mx-auto space-y-8">
        <h1 className="text-2xl font-semibold text-gray-900">
          Company overview <span className="text-base font-normal text-gray-500">({data.period})</span>
        </h1>

        {/* KPI cards */}
        <section aria-label="Company-wide KPIs" className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <KpiCard label="Applications this month" value={String(data.total_applications)} />
          <KpiCard label="Screening pass rate" value={pct(data.screening_pass_rate)} />
          <KpiCard label="Avg evaluation score" value={num(data.avg_evaluation_score)} />
        </section>

        {/* Job list (beneath the KPI cards) */}
        <section aria-labelledby="jobs-h">
          <h2 id="jobs-h" className="text-lg font-medium text-gray-900 mb-3">Jobs</h2>
          <ul className="bg-white rounded-lg shadow divide-y">
            {data.jobs.length === 0 && <li className="p-4 text-gray-500">No jobs yet.</li>}
            {data.jobs.map((job) => (
              <li key={job.id} className="p-4 flex items-center justify-between">
                <button onClick={() => onSelectJob(job.id)} className="text-left">
                  <span className="font-medium text-gray-900">{job.title}</span>
                  <span className="ml-2 text-xs uppercase text-gray-500">{job.status}</span>
                </button>
                <button
                  onClick={() => onViewJobAnalytics(job.id)}
                  className="text-blue-600 underline text-sm"
                >
                  Analytics
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
