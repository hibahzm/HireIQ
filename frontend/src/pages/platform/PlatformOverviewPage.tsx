import { useEffect, useMemo, useState } from "react";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import PageHeader from "../../components/ui/PageHeader";
import { TrashIcon } from "../../components/ui/icons";
import { api, ApiError, type PlatformOverview } from "../../services/api";

interface Props {
  token: string;
}

function formatTokens(value: number) {
  return value.toLocaleString();
}

function formatCost(value: number) {
  return `$${value.toFixed(4)}`;
}

export default function PlatformOverviewPage({ token }: Props) {
  const [data, setData] = useState<PlatformOverview | null>(null);
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function loadOverview() {
    setError(null);
    try {
      const overview = await api.platform.overview(token);
      setData(overview);
      setSelectedCompanyId((current) => {
        if (current && overview.companies.some((company) => company.id === current)) return current;
        return overview.companies[0]?.id ?? null;
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load platform overview");
    }
  }

  useEffect(() => {
    void loadOverview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const selectedCompany = data?.companies.find((company) => company.id === selectedCompanyId) ?? null;
  const selectedUsage = useMemo(
    () => data?.usage.filter((item) => item.company_id === selectedCompanyId) ?? [],
    [data, selectedCompanyId]
  );
  const selectedAuditEvents = useMemo(
    () => data?.audit_events.filter((item) => item.company_id === selectedCompanyId) ?? [],
    [data, selectedCompanyId]
  );

  const totals = useMemo(() => {
    const companies = data?.companies ?? [];
    return companies.reduce(
      (acc, company) => ({
        promptTokens: acc.promptTokens + company.prompt_tokens,
        completionTokens: acc.completionTokens + company.completion_tokens,
        cost: acc.cost + company.estimated_cost_usd,
        activity: acc.activity + company.activity_events,
      }),
      { promptTokens: 0, completionTokens: 0, cost: 0, activity: 0 }
    );
  }, [data]);

  async function handleDeleteCompany() {
    if (!selectedCompany) return;
    const ok = confirm(
      `Delete "${selectedCompany.name}" and all related users, jobs, applications, usage, and stored files?`
    );
    if (!ok) return;
    setDeletingId(selectedCompany.id);
    setError(null);
    try {
      await api.platform.deleteCompany(token, selectedCompany.id);
      await loadOverview();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to delete company");
    } finally {
      setDeletingId(null);
    }
  }

  if (error) return <p className="text-red-600" role="alert">{error}</p>;
  if (!data) return <p className="text-primary-500">Loading platform overview...</p>;

  const totalTokens = totals.promptTokens + totals.completionTokens;

  return (
    <div className="space-y-6">
      <PageHeader title="Platform" description="Companies, usage, and platform operations." />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-4">
        <Card className="p-5">
          <p className="text-sm text-primary-500">Customer companies</p>
          <p className="mt-1 text-3xl font-bold text-primary-800">{data.companies.length}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-primary-500">Tokens this month</p>
          <p className="mt-1 text-3xl font-bold text-primary-800">{formatTokens(totalTokens)}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-primary-500">Estimated cost</p>
          <p className="mt-1 text-3xl font-bold text-primary-800">{formatCost(totals.cost)}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-primary-500">Activity events</p>
          <p className="mt-1 text-3xl font-bold text-primary-800">{totals.activity}</p>
        </Card>
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)]">
        <Card className="overflow-hidden">
          <div className="border-b border-primary-100 px-5 py-4">
            <h2 className="text-base font-semibold text-primary-800">Companies</h2>
          </div>
          {data.companies.length === 0 ? (
            <p className="px-5 py-8 text-sm text-primary-500">
              No customer companies yet. The internal platform manager company is hidden here.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-primary-100 bg-primary-50/50 text-left text-xs uppercase tracking-wide text-primary-400">
                  <th className="px-5 py-3 font-semibold">Company</th>
                  <th className="px-5 py-3 font-semibold">Usage</th>
                  <th className="px-5 py-3 font-semibold">Cost</th>
                  <th className="px-5 py-3 font-semibold">Activity</th>
                  <th className="px-5 py-3 font-semibold">Last activity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-primary-100">
                {data.companies.map((company) => {
                  const isSelected = company.id === selectedCompanyId;
                  const tokens = company.prompt_tokens + company.completion_tokens;
                  return (
                    <tr
                      key={company.id}
                      className={`cursor-pointer transition-colors ${
                        isSelected ? "bg-brand-50" : "hover:bg-primary-50/60"
                      }`}
                      onClick={() => setSelectedCompanyId(company.id)}
                    >
                      <td className="px-5 py-3">
                        <p className="font-semibold text-primary-800">{company.name}</p>
                        <p className="font-mono text-xs text-primary-400">{company.id.slice(0, 8)}</p>
                      </td>
                      <td className="px-5 py-3 text-primary-700">{formatTokens(tokens)}</td>
                      <td className="px-5 py-3 text-primary-700">{formatCost(company.estimated_cost_usd)}</td>
                      <td className="px-5 py-3 text-primary-700">{company.activity_events}</td>
                      <td className="px-5 py-3 text-primary-500">
                        {company.last_activity_at
                          ? new Date(company.last_activity_at).toLocaleString()
                          : "-"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Card>

        <Card className="p-5">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-primary-800">
                {selectedCompany ? selectedCompany.name : "Company details"}
              </h2>
              {selectedCompany && (
                <p className="font-mono text-xs text-primary-400">{selectedCompany.id}</p>
              )}
            </div>
            {selectedCompany && (
              <Button
                size="sm"
                variant="danger"
                loading={deletingId === selectedCompany.id}
                onClick={handleDeleteCompany}
              >
                <TrashIcon className="h-4 w-4" /> Delete
              </Button>
            )}
          </div>

          {!selectedCompany ? (
            <p className="text-sm text-primary-500">Select a company to inspect usage and activity.</p>
          ) : (
            <div className="space-y-6">
              <div className="grid grid-cols-3 gap-3 text-sm">
                <div>
                  <p className="text-primary-400">Prompt</p>
                  <p className="font-semibold text-primary-800">
                    {formatTokens(selectedCompany.prompt_tokens)}
                  </p>
                </div>
                <div>
                  <p className="text-primary-400">Completion</p>
                  <p className="font-semibold text-primary-800">
                    {formatTokens(selectedCompany.completion_tokens)}
                  </p>
                </div>
                <div>
                  <p className="text-primary-400">Cost</p>
                  <p className="font-semibold text-primary-800">
                    {formatCost(selectedCompany.estimated_cost_usd)}
                  </p>
                </div>
              </div>

              <div>
                <h3 className="mb-2 text-sm font-semibold text-primary-800">Usage by agent</h3>
                {selectedUsage.length === 0 ? (
                  <p className="text-sm text-primary-500">No usage recorded this month.</p>
                ) : (
                  <div className="space-y-2">
                    {selectedUsage.map((item) => (
                      <div
                        key={`${item.company_id}-${item.agent_type}`}
                        className="flex items-center justify-between rounded-lg bg-primary-50 px-3 py-2 text-sm"
                      >
                        <span className="font-medium text-primary-700">{item.agent_type}</span>
                        <span className="text-primary-600">
                          {formatTokens(item.prompt_tokens + item.completion_tokens)} /{" "}
                          {formatCost(item.estimated_cost_usd)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <h3 className="mb-2 text-sm font-semibold text-primary-800">Activity by event</h3>
                {selectedAuditEvents.length === 0 ? (
                  <p className="text-sm text-primary-500">No activity recorded this month.</p>
                ) : (
                  <div className="space-y-2">
                    {selectedAuditEvents.map((item) => (
                      <div
                        key={`${item.company_id}-${item.event_type}`}
                        className="flex items-center justify-between rounded-lg bg-primary-50 px-3 py-2 text-sm"
                      >
                        <span className="font-medium text-primary-700">{item.event_type}</span>
                        <span className="text-primary-600">{item.count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </Card>
      </section>
    </div>
  );
}
