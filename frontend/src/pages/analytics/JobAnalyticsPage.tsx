import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, ApiError, type JobAnalytics } from "../../services/api";

interface Props {
  token: string;
  jobId: string;
  onBack?: () => void;
}

const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);
const num = (v: number | null) => (v === null ? "—" : String(v));
const secs = (t: { p50: number; p95: number } | null) =>
  t === null ? "—" : `p50 ${Math.round(t.p50)}s · p95 ${Math.round(t.p95)}s`;

export default function JobAnalyticsPage({ token, jobId }: Props) {
  const [data, setData] = useState<JobAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api.analytics
      .job(token, jobId)
      .then((d) => active && setData(d))
      .catch((e) =>
        active && setError(e instanceof ApiError ? e.message : "Failed to load analytics")
      );
    return () => {
      active = false;
    };
  }, [token, jobId]);

  if (error) {
    return <p className="text-red-600" role="alert">{error}</p>;
  }
  if (!data) {
    return <div className="text-primary-500">Loading analytics…</div>;
  }

  const funnelData = [
    { stage: "Received", count: data.funnel.received },
    { stage: "Qualified", count: data.funnel.qualified },
    { stage: "Interviewed", count: data.funnel.interviewed },
    { stage: "Evaluated", count: data.funnel.evaluated },
  ];

  return (
    <div className="max-w-4xl">
      <div className="space-y-8">
        <h1 className="text-2xl font-bold tracking-tight text-primary-800">Job analytics</h1>

        {/* Funnel */}
        <section aria-labelledby="funnel-h" className="bg-white rounded-lg shadow p-6">
          <h2 id="funnel-h" className="text-lg font-medium mb-4">Hiring funnel</h2>
          <div className="h-64" aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={funnelData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="stage" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="#2563eb" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          {/* Accessible fallback (WCAG 2.1 AA) */}
          <table className="w-full mt-4 text-sm">
            <caption className="sr-only">Funnel stage counts</caption>
            <thead>
              <tr className="text-left text-gray-600">
                <th scope="col">Stage</th><th scope="col">Count</th>
              </tr>
            </thead>
            <tbody>
              {funnelData.map((r) => (
                <tr key={r.stage}><td>{r.stage}</td><td>{r.count}</td></tr>
              ))}
            </tbody>
          </table>
        </section>

        {/* Rates + score + timings */}
        <section aria-labelledby="rates-h" className="bg-white rounded-lg shadow p-6">
          <h2 id="rates-h" className="text-lg font-medium mb-4">Rates &amp; timing</h2>
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div><dt className="text-gray-600">Qualification rate</dt><dd>{pct(data.qualification_rate)}</dd></div>
            <div><dt className="text-gray-600">Interview-completion rate</dt><dd>{pct(data.interview_completion_rate)}</dd></div>
            <div><dt className="text-gray-600">Avg evaluation score</dt><dd>{num(data.avg_evaluation_score)}</dd></div>
            <div><dt className="text-gray-600">Time to screen</dt><dd>{secs(data.time_to_screen_seconds)}</dd></div>
            <div><dt className="text-gray-600">Time to evaluate</dt><dd>{secs(data.time_to_evaluate_seconds)}</dd></div>
          </dl>
        </section>

        {/* Score distribution */}
        <section aria-labelledby="dist-h" className="bg-white rounded-lg shadow p-6">
          <h2 id="dist-h" className="text-lg font-medium mb-4">Evaluation-score distribution</h2>
          <div className="h-64" aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.score_distribution}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="band" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="#16a34a" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="w-full mt-4 text-sm">
            <caption className="sr-only">Evaluation score distribution</caption>
            <thead>
              <tr className="text-left text-gray-600"><th scope="col">Band</th><th scope="col">Count</th></tr>
            </thead>
            <tbody>
              {data.score_distribution.map((b) => (
                <tr key={b.band}><td>{b.band}</td><td>{b.count}</td></tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
