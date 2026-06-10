import { useEffect, useState } from "react";
import { api, ApiError, type CompanyOverview } from "../../services/api";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
import PageHeader from "../../components/ui/PageHeader";
import { PlusIcon } from "../../components/ui/icons";

interface Props {
  token: string;
  onSelectJob: (jobId: string) => void;
  onViewJobAnalytics: (jobId: string) => void;
  onManageJobs: () => void;
}

const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);
const num = (v: number | null) => (v === null ? "—" : String(v));

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-6">
      <div className="text-sm text-primary-500">{label}</div>
      <div className="mt-1 text-3xl font-bold text-primary-800">{value}</div>
    </Card>
  );
}

export default function CompanyOverviewPage({ token, onSelectJob, onViewJobAnalytics, onManageJobs }: Props) {
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
    return <div className="text-red-600" role="alert">{error}</div>;
  }
  if (!data) {
    return <div className="text-primary-500">Loading overview…</div>;
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Company overview"
        description={`Hiring activity for ${data.period}.`}
        actions={
          <Button onClick={onManageJobs}>
            <PlusIcon /> Create / manage jobs
          </Button>
        }
      />

      {/* KPI cards */}
      <section aria-label="Company-wide KPIs" className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <KpiCard label="Applications this month" value={String(data.total_applications)} />
        <KpiCard label="Screening pass rate" value={pct(data.screening_pass_rate)} />
        <KpiCard label="Avg evaluation score" value={num(data.avg_evaluation_score)} />
      </section>

      {/* Job list (beneath the KPI cards) */}
      <section aria-labelledby="jobs-h">
        <h2 id="jobs-h" className="mb-3 text-lg font-semibold text-primary-800">Jobs</h2>
        <Card className="divide-y divide-primary-100 overflow-hidden">
          {data.jobs.length === 0 && <p className="p-4 text-sm text-primary-500">No jobs yet.</p>}
          {data.jobs.map((job) => (
            <div key={job.id} className="flex items-center justify-between p-4 transition-colors hover:bg-primary-50/60">
              <button onClick={() => onSelectJob(job.id)} className="flex items-center gap-2 text-left cursor-pointer">
                <span className="font-semibold text-primary-800 hover:text-brand-700">{job.title}</span>
                <Badge status={job.status} />
              </button>
              <Button size="sm" variant="ghost" onClick={() => onViewJobAnalytics(job.id)}>
                Analytics
              </Button>
            </div>
          ))}
        </Card>
      </section>
    </div>
  );
}
