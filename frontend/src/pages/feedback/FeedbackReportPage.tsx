import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, FeedbackReport, ApiError } from "../../services/api";

function ScoreBar({ score }: { score: number }) {
  const color =
    score >= 75 ? "bg-green-500" : score >= 50 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 bg-gray-100 rounded-full h-2.5">
        <div className={`h-2.5 rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-sm font-semibold text-gray-700 w-10 text-right">
        {score}<span className="font-normal text-gray-400">/100</span>
      </span>
    </div>
  );
}

function ExpiredState() {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-10 max-w-md text-center">
        <div className="w-14 h-14 rounded-full bg-orange-100 flex items-center justify-center mx-auto mb-5">
          <svg className="w-7 h-7 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <h1 className="text-xl font-bold text-gray-900 mb-2">Link expired</h1>
        <p className="text-gray-500 text-sm">
          This feedback link is no longer valid. Feedback links expire after 30 days.
          Please contact the employer if you need further information.
        </p>
      </div>
    </div>
  );
}

function NotFoundState() {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-10 max-w-md text-center">
        <h1 className="text-xl font-bold text-gray-900 mb-2">Link not found</h1>
        <p className="text-gray-500 text-sm">
          This feedback link is invalid. Please check the link in your email and try again.
        </p>
      </div>
    </div>
  );
}

export default function FeedbackReportPage() {
  const { token = "" } = useParams<{ token: string }>();
  const [report, setReport] = useState<FeedbackReport | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "expired" | "notfound" | "error">("loading");

  useEffect(() => {
    if (!token) { setState("notfound"); return; }
    api.feedback
      .get(token)
      .then((r) => { setReport(r); setState("ok"); })
      .catch((e: ApiError) => {
        if (e.status === 410) setState("expired");
        else if (e.status === 404) setState("notfound");
        else setState("error");
      });
  }, [token]);

  if (state === "loading") {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-500">Loading your feedback…</p>
      </div>
    );
  }
  if (state === "expired") return <ExpiredState />;
  if (state === "notfound" || state === "error" || !report) return <NotFoundState />;

  const overall = report.overall_score;
  const overallColor =
    overall >= 75 ? "text-green-600" : overall >= 50 ? "text-yellow-600" : "text-red-600";

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-2xl mx-auto space-y-8">

        {/* Header */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm text-gray-500 mb-1">Interview feedback for</p>
              <h1 className="text-2xl font-bold text-gray-900">{report.job_title}</h1>
            </div>
            <div className="text-center flex-shrink-0">
              <div className={`text-4xl font-bold ${overallColor}`}>{overall}</div>
              <div className="text-xs text-gray-400">Overall score</div>
            </div>
          </div>
          <p className="mt-4 text-sm text-gray-500">
            This report summarises your performance across each evaluation area.
            It is provided for your personal development and does not include the
            hiring recommendation.
          </p>
        </div>

        {/* Dimension scores */}
        {report.dimension_scores.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-5">Performance by area</h2>
            <div className="space-y-4">
              {report.dimension_scores.map((d) => (
                <div key={d.dimension}>
                  <div className="flex justify-between items-center mb-1.5">
                    <span className="text-sm font-medium text-gray-700">{d.dimension}</span>
                  </div>
                  <ScoreBar score={d.score} />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Summary */}
        {report.summary && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 space-y-6">
            <h2 className="text-lg font-semibold text-gray-900">Feedback summary</h2>

            {report.summary.strengths && (
              <div>
                <h3 className="text-sm font-semibold text-green-700 uppercase tracking-wide mb-2">
                  Strengths
                </h3>
                <p className="text-gray-700 text-sm leading-relaxed">
                  {report.summary.strengths}
                </p>
              </div>
            )}

            {report.summary.areas_for_improvement && (
              <div>
                <h3 className="text-sm font-semibold text-blue-700 uppercase tracking-wide mb-2">
                  Areas for improvement
                </h3>
                <p className="text-gray-700 text-sm leading-relaxed">
                  {report.summary.areas_for_improvement}
                </p>
              </div>
            )}
          </div>
        )}

        <p className="text-center text-xs text-gray-400 pb-4">
          Powered by HireIQ · This link expires 30 days after your evaluation
        </p>
      </div>
    </div>
  );
}
