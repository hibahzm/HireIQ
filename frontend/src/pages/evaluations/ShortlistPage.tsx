import { useEffect, useState } from "react";
import { api, ShortlistItem, ApiError } from "../../services/api";

const RECOMMENDATION_STYLES: Record<string, string> = {
  hire: "bg-green-100 text-green-800",
  uncertain: "bg-yellow-100 text-yellow-800",
  no_hire: "bg-red-100 text-red-700",
};

const RECOMMENDATION_LABELS: Record<string, string> = {
  hire: "Hire",
  uncertain: "Uncertain",
  no_hire: "No Hire",
};

interface Props {
  token: string;
  jobId: string;
  onSelectEvaluation: (evaluationId: string) => void;
  onBack?: () => void;
}

export default function ShortlistPage({ token, jobId, onSelectEvaluation }: Props) {
  const [items, setItems] = useState<ShortlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.evaluations
      .listByJob(token, jobId)
      .then(setItems)
      .catch((e: ApiError) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, jobId]);

  if (loading) return <div className="p-8 text-gray-500">Loading evaluations…</div>;

  return (
    <div className="max-w-4xl">
      <h1 className="mb-6 text-2xl font-bold tracking-tight text-primary-800">Candidate shortlist</h1>

      {error && <p className="text-red-600 mb-4" role="alert">{error}</p>}

      {items.length === 0 ? (
        <p className="text-gray-500">No evaluations yet. Evaluations appear after candidates complete their interviews.</p>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <button
              key={item.evaluation_id}
              onClick={() => onSelectEvaluation(item.evaluation_id)}
              className="w-full text-left bg-white border border-gray-200 rounded-lg p-4 hover:border-blue-400 hover:shadow-sm transition-all"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center font-semibold text-blue-700">
                    {item.candidate.full_name.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <div className="font-medium text-gray-900">{item.candidate.full_name}</div>
                    <div className="text-sm text-gray-500">
                      {new Date(item.created_at).toLocaleDateString()}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {item.confidence_flag && (
                    <span
                      title="Low confidence evaluation — limited evidence from interview"
                      className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full"
                    >
                      Low confidence
                    </span>
                  )}
                  <span
                    className={`text-xs font-medium px-2.5 py-1 rounded-full ${RECOMMENDATION_STYLES[item.recommendation] ?? "bg-gray-100 text-gray-700"}`}
                  >
                    {RECOMMENDATION_LABELS[item.recommendation] ?? item.recommendation}
                  </span>
                  <div className="text-right">
                    <div className="text-xl font-bold text-gray-900">{item.overall_score}</div>
                    <div className="text-xs text-gray-500">/ 100</div>
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
