import { useEffect, useState } from "react";
import {
  api,
  EvaluationDetail,
  DimensionScore,
  ConsistencyFlag,
  ApiError,
} from "../../services/api";

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
  evaluationId: string;
  onBack: () => void;
}

function ScoreBar({ score }: { score: number }) {
  const color = score >= 75 ? "bg-green-500" : score >= 50 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-100 rounded-full h-2">
        <div className={`h-2 rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-sm font-medium text-gray-700 w-8 text-right">{score}</span>
    </div>
  );
}

function DimensionScoresPanel({ dimensions }: { dimensions: DimensionScore[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <section>
      <h2 className="text-lg font-semibold text-gray-900 mb-3">Dimension Scores</h2>
      <div className="space-y-3">
        {dimensions.map((d) => (
          <div key={d.dimension} className="border border-gray-200 rounded-lg p-3">
            <div className="flex items-center justify-between mb-1">
              <button
                onClick={() => setExpanded(expanded === d.dimension ? null : d.dimension)}
                className="font-medium text-gray-800 hover:text-blue-600 text-left"
              >
                {d.dimension}
              </button>
              <span className="text-sm text-gray-500">{d.score}/100</span>
            </div>
            <ScoreBar score={d.score} />
            {expanded === d.dimension && d.evidence_quotes.length > 0 && (
              <ul className="mt-2 space-y-1">
                {d.evidence_quotes.map((q, i) => (
                  <li key={i} className="text-sm text-gray-600 pl-3 border-l-2 border-blue-200 italic">
                    "{q}"
                  </li>
                ))}
              </ul>
            )}
            {expanded === d.dimension && d.evidence_quotes.length === 0 && (
              <p className="mt-2 text-sm text-gray-400 italic">No evidence quotes available.</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function ConsistencyFlagsPanel({ flags }: { flags: ConsistencyFlag[] }) {
  if (flags.length === 0) return null;
  return (
    <section>
      <h2 className="text-lg font-semibold text-gray-900 mb-3">Consistency Flags</h2>
      <div className="space-y-2">
        {flags.map((f, i) => (
          <div key={i} className="border border-orange-200 rounded-lg p-3 bg-orange-50">
            <div className="flex items-start gap-2">
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  f.flag_type === "contradiction"
                    ? "bg-red-100 text-red-700"
                    : "bg-yellow-100 text-yellow-700"
                }`}
              >
                {f.flag_type === "contradiction" ? "Contradiction" : "Unverified"}
              </span>
              <div className="flex-1 text-sm text-gray-700">
                <p className="font-medium mb-1">{f.claim}</p>
                {f.cv_statement && <p className="text-gray-500">CV: {f.cv_statement}</p>}
                {f.interview_statement && (
                  <p className="text-gray-500">Interview: {f.interview_statement}</p>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function CommunicationPanel({
  quality,
}: {
  quality: EvaluationDetail["communication_quality"];
}) {
  const metrics = [
    { label: "Response Depth", value: quality.response_depth },
    { label: "Filler Words", value: quality.filler_word_frequency, invert: true },
    { label: "Deflections", value: quality.deflection_frequency, invert: true },
  ];
  return (
    <section>
      <h2 className="text-lg font-semibold text-gray-900 mb-3">Communication Quality</h2>
      <div className="grid grid-cols-3 gap-3">
        {metrics.map(({ label, value, invert }) => {
          const pct = Math.round(value * 100);
          const color = invert
            ? value < 0.1 ? "text-green-600" : value < 0.25 ? "text-yellow-600" : "text-red-600"
            : value >= 0.7 ? "text-green-600" : value >= 0.4 ? "text-yellow-600" : "text-red-600";
          return (
            <div key={label} className="border border-gray-200 rounded-lg p-3 text-center">
              <div className={`text-2xl font-bold ${color}`}>{pct}%</div>
              <div className="text-xs text-gray-500 mt-1">{label}</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

// The transcript audio endpoint requires Bearer auth, which a plain <audio src>
// can't send. Fetch the clip with the token, then play it from an object URL.
function AuthAudio({ url, token }: { url: string; token: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    fetch(`${API_BASE}${url}`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url, token]);

  if (failed) return <p className="text-xs text-primary-400">Audio unavailable</p>;
  if (!src) return <p className="text-xs text-primary-400">Loading audio…</p>;
  return <audio src={src} controls className="h-8 w-full" />;
}

function TranscriptPanel({
  transcript,
  token,
}: {
  transcript: EvaluationDetail["transcript"];
  token: string;
}) {
  return (
    <section>
      <h2 className="text-lg font-semibold text-gray-900 mb-3">Transcript</h2>
      <div className="space-y-3">
        {transcript.map((turn) => {
          const isAI = turn.speaker === "ai";
          return (
            <div
              key={turn.turn_index}
              className={`flex gap-3 ${isAI ? "flex-row" : "flex-row-reverse"}`}
            >
              <div
                title={isAI ? "Sila (AI interviewer)" : "Candidate"}
                className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-semibold ${
                  isAI ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-700"
                }`}
              >
                {isAI ? "S" : "C"}
              </div>
              <div
                className={`flex-1 max-w-xl rounded-lg px-4 py-2 ${
                  isAI ? "bg-blue-50" : "bg-gray-50"
                }`}
              >
                <p className="text-sm text-gray-800">{turn.content_text}</p>
                {turn.audio_url && (
                  <div className="mt-2">
                    <AuthAudio url={turn.audio_url} token={token} />
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function EvaluationDetailPage({ token, evaluationId }: Props) {
  const [evaluation, setEvaluation] = useState<EvaluationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.evaluations
      .get(token, evaluationId)
      .then(setEvaluation)
      .catch((e: ApiError) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, evaluationId]);

  if (loading) return <div className="text-primary-500">Loading evaluation…</div>;
  if (error) return <div className="text-red-600">{error}</div>;
  if (!evaluation) return null;

  return (
    <div className="max-w-3xl space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Evaluation Detail</h1>
          <p className="text-sm text-gray-500 mt-1">
            {new Date(evaluation.created_at).toLocaleString()}
          </p>
        </div>
        <div className="text-right">
          <div className="text-4xl font-bold text-gray-900">{evaluation.overall_score}</div>
          <div className="text-sm text-gray-500">/ 100</div>
          <span
            className={`mt-1 inline-block text-xs font-medium px-2.5 py-1 rounded-full ${
              RECOMMENDATION_STYLES[evaluation.recommendation] ?? "bg-gray-100 text-gray-700"
            }`}
          >
            {RECOMMENDATION_LABELS[evaluation.recommendation] ?? evaluation.recommendation}
          </span>
        </div>
      </div>

      {/* Confidence warning */}
      {evaluation.confidence_flag && (
        <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
          <p className="text-sm font-medium text-orange-800">Low Confidence Evaluation</p>
          {evaluation.confidence_reason && (
            <p className="text-sm text-orange-700 mt-1">{evaluation.confidence_reason}</p>
          )}
        </div>
      )}

      {/* AI-generated summary */}
      {evaluation.summary && (
        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Summary</h2>
          <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-700 whitespace-pre-line">
            {evaluation.summary}
          </div>
        </section>
      )}

      <DimensionScoresPanel dimensions={evaluation.dimension_scores} />
      <ConsistencyFlagsPanel flags={evaluation.consistency_flags} />
      <CommunicationPanel quality={evaluation.communication_quality} />
      <TranscriptPanel transcript={evaluation.transcript} token={token} />
    </div>
  );
}
