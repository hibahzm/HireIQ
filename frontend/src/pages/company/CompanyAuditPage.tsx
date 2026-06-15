import { useEffect, useState } from "react";
import { api, ApiError, type AuditEvent } from "../../services/api";

interface Props {
  token: string;
}

const ACTOR_COLORS: Record<string, string> = {
  user: "bg-blue-100 text-blue-800",
  system: "bg-gray-100 text-gray-700",
  candidate: "bg-purple-100 text-purple-800",
};

function formatEventType(eventType: string): string {
  return eventType.replace(/[._]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatTimestamp(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export default function CompanyAuditPage({ token }: Props) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.company
      .audit(token, 200)
      .then(setEvents)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load activity log"))
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <div className="max-w-4xl">
      <h1 className="mb-1 text-2xl font-bold tracking-tight text-primary-800">Activity log</h1>
      <p className="mb-6 text-sm text-primary-500">
        A record of actions in your company — invitations, screening, interviews, evaluations and CV
        access. Most recent first.
      </p>

      {loading && <div className="text-primary-500">Loading…</div>}
      {error && <div className="text-red-600">{error}</div>}

      {!loading && !error && events.length === 0 && (
        <div className="rounded-lg border border-primary-200 bg-white p-8 text-center text-sm text-primary-500">
          No activity recorded yet.
        </div>
      )}

      {!loading && !error && events.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-primary-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-primary-50 text-xs uppercase tracking-wide text-primary-500">
              <tr>
                <th className="px-5 py-3 font-semibold">Event</th>
                <th className="px-5 py-3 font-semibold">Actor</th>
                <th className="px-5 py-3 font-semibold">Entity</th>
                <th className="px-5 py-3 font-semibold">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-primary-100">
              {events.map((e) => (
                <tr key={e.id} className="hover:bg-primary-50/50">
                  <td className="px-5 py-3 font-medium text-primary-800">
                    {formatEventType(e.event_type)}
                  </td>
                  <td className="px-5 py-3">
                    <span
                      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
                        ACTOR_COLORS[e.actor_type] ?? "bg-gray-100 text-gray-700"
                      }`}
                    >
                      {e.actor_type}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-primary-600">{e.entity_type ?? "—"}</td>
                  <td className="px-5 py-3 whitespace-nowrap text-primary-500">
                    {formatTimestamp(e.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
