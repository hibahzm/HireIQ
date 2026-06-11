import { useEffect, useState } from "react";
import Card from "../../components/ui/Card";
import PageHeader from "../../components/ui/PageHeader";
import { api, ApiError, type PlatformOverview } from "../../services/api";

interface Props {
  token: string;
}

export default function PlatformOverviewPage({ token }: Props) {
  const [data, setData] = useState<PlatformOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api.platform
      .overview(token)
      .then((d) => active && setData(d))
      .catch((e) =>
        active && setError(e instanceof ApiError ? e.message : "Failed to load platform overview")
      );
    return () => {
      active = false;
    };
  }, [token]);

  if (error) return <p className="text-red-600" role="alert">{error}</p>;
  if (!data) return <p className="text-primary-500">Loading platform overview...</p>;

  const totalCost = data.usage.reduce((sum, item) => sum + item.estimated_cost_usd, 0);
  const totalTokens = data.usage.reduce(
    (sum, item) => sum + item.prompt_tokens + item.completion_tokens,
    0
  );

  return (
    <div className="space-y-8">
      <PageHeader title="Platform overview" description="Operational aggregates across tenants." />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card className="p-5">
          <p className="text-sm text-primary-500">Companies</p>
          <p className="mt-1 text-3xl font-bold text-primary-800">{data.companies.length}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-primary-500">Tokens this month</p>
          <p className="mt-1 text-3xl font-bold text-primary-800">{totalTokens}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-primary-500">Estimated cost</p>
          <p className="mt-1 text-3xl font-bold text-primary-800">${totalCost.toFixed(4)}</p>
        </Card>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-primary-800">Companies</h2>
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-primary-100 bg-primary-50/50 text-left text-xs uppercase tracking-wide text-primary-400">
                <th className="px-5 py-3 font-semibold">Company</th>
                <th className="px-5 py-3 font-semibold">Activity</th>
                <th className="px-5 py-3 font-semibold">Job events</th>
                <th className="px-5 py-3 font-semibold">Last activity</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-primary-100">
              {data.companies.map((company) => (
                <tr key={company.id}>
                  <td className="px-5 py-3 font-medium text-primary-800">{company.name}</td>
                  <td className="px-5 py-3 text-primary-600">{company.activity_events}</td>
                  <td className="px-5 py-3 text-primary-600">{company.job_events}</td>
                  <td className="px-5 py-3 text-primary-500">
                    {company.last_activity_at
                      ? new Date(company.last_activity_at).toLocaleString()
                      : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="mb-3 text-lg font-semibold text-primary-800">Usage this month</h2>
          {data.usage.length === 0 ? (
            <p className="text-sm text-primary-500">No usage recorded yet.</p>
          ) : (
            <div className="space-y-2">
              {data.usage.map((item, i) => (
                <div key={`${item.company_id}-${item.agent_type}-${i}`} className="flex justify-between text-sm">
                  <span className="text-primary-700">{item.agent_type}</span>
                  <span className="font-medium text-primary-800">
                    {item.prompt_tokens + item.completion_tokens} tokens / $
                    {item.estimated_cost_usd.toFixed(4)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-5">
          <h2 className="mb-3 text-lg font-semibold text-primary-800">Audit events</h2>
          <div className="space-y-2">
            {data.audit_events.map((item) => (
              <div key={item.event_type} className="flex justify-between text-sm">
                <span className="text-primary-700">{item.event_type}</span>
                <span className="font-medium text-primary-800">{item.count}</span>
              </div>
            ))}
          </div>
        </Card>
      </section>
    </div>
  );
}
