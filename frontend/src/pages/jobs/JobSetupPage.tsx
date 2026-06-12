import { useEffect, useRef, useState } from "react";
import { api, ApiError, type JobCriteriaInput } from "../../services/api";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import PageHeader from "../../components/ui/PageHeader";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface Props {
  token: string;
  jobId: string;
  onActivated: () => void;
  onBack: () => void;
}

export default function JobSetupPage({ token, jobId, onActivated }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<string>("in_progress");
  const [criteriaDraft, setCriteriaDraft] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [activating, setActivating] = useState(false);
  const [savingManual, setSavingManual] = useState(false);
  const [manualCriteria, setManualCriteria] = useState(`{
  "required_skills": [{"skill": "Node.js", "priority": "required"}],
  "optional_skills": [],
  "experience_level": "mid",
  "min_years_experience": 2,
  "evaluation_dimensions": [{"name": "Technical depth", "weight": 50}, {"name": "Communication", "weight": 50}],
  "dealbreakers": [],
  "min_screening_score": 60
}`);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Restore a previously started setup chat (closing the tab mid-setup loses
  // nothing — the conversation is persisted server-side). Only when no prior
  // conversation exists do we kick off the first AI turn, which the backend
  // seeds with the recruiter-provided job description.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const conv = await api.jobs.setupConversation(token, jobId);
        if (cancelled) return;
        const restored = conv.messages.filter(
          (m) =>
            !(m.role === "user" && m.content.startsWith("Here is the job description for this role."))
        );
        if (restored.length) setMessages(restored);
        if (conv.criteria) setCriteriaDraft(conv.criteria);
        if (conv.job_status === "active") {
          setStatus("activated");
          return;
        }
        if (conv.status === "completed" && conv.criteria) {
          setStatus("completed");
          return;
        }
        if (conv.status === "failed") {
          setStatus("failed");
          return;
        }
        if (!conv.messages.length) {
          await sendTurn("");
        }
      } catch {
        if (!cancelled) await sendTurn("");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendTurn(userMessage: string) {
    if (sending) return;
    setSending(true);
    setError(null);

    if (userMessage) {
      setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    }

    try {
      const res = await api.jobs.setupTurn(token, jobId, { user_message: userMessage });
      setMessages((prev) => [...prev, { role: "assistant", content: res.message }]);
      setStatus(res.status === "completed" && res.job_status === "active" ? "activated" : res.status);
      if (res.criteria_draft) setCriteriaDraft(res.criteria_draft);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to get AI response");
    } finally {
      setSending(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const msg = input.trim();
    if (!msg) return;
    setInput("");
    await sendTurn(msg);
  }

  async function handleActivate() {
    setActivating(true);
    setError(null);
    try {
      await api.jobs.activate(token, jobId);
      setActivating(false);
      setStatus("activated");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Activation failed");
      setActivating(false);
    }
  }

  async function handleRetrySetup() {
    setStatus("in_progress");
    await sendTurn("");
  }

  async function handleSaveManualCriteria() {
    setSavingManual(true);
    setError(null);
    try {
      const parsed = JSON.parse(manualCriteria) as JobCriteriaInput;
      if (!Array.isArray(parsed.required_skills) || !Array.isArray(parsed.evaluation_dimensions)) {
        throw new Error("required_skills and evaluation_dimensions must be arrays");
      }
      await api.jobs.saveCriteria(token, jobId, parsed);
      setCriteriaDraft(parsed);
      setStatus("completed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save criteria");
    } finally {
      setSavingManual(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="AI-guided job setup"
        description="The assistant reads your job description, extracts evaluation criteria, and asks only about what's missing."
      />

      <Card className="flex h-[calc(100vh-15rem)] flex-col overflow-hidden">
        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          {messages.length === 0 && !sending && (
            <p className="text-sm text-primary-400">Starting setup…</p>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-brand-600 text-white"
                    : "bg-primary-100 text-primary-800"
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="rounded-2xl bg-primary-100 px-4 py-2.5 text-sm text-primary-400">
                Thinking…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {error && (
          <p className="border-t border-primary-100 px-5 py-2 text-sm text-red-600" role="alert">
            {error}
          </p>
        )}

        {status === "completed" ? (
          <div className="border-t border-primary-100 bg-primary-50/50 p-5">
            <p className="mb-3 text-sm text-primary-600">
              Setup complete. Review the extracted criteria and activate the job.
            </p>
            {!!criteriaDraft && (
              <pre className="mb-3 max-h-44 overflow-auto rounded-lg border border-primary-200 bg-surface p-3 text-xs text-primary-700">
                {JSON.stringify(criteriaDraft, null, 2)}
              </pre>
            )}
            <Button
              onClick={handleActivate}
              loading={activating}
              className="w-full bg-green-600 hover:bg-green-700"
            >
              Confirm &amp; activate job
            </Button>
          </div>
        ) : status === "activated" ? (
          <div className="border-t border-primary-100 bg-green-50/60 p-5">
            <p className="mb-3 text-sm font-medium text-green-800">
              Setup complete. This job is active and ready to receive applications.
            </p>
            {!!criteriaDraft && (
              <pre className="mb-3 max-h-44 overflow-auto rounded-lg border border-green-200 bg-white p-3 text-xs text-primary-700">
                {JSON.stringify(criteriaDraft, null, 2)}
              </pre>
            )}
            <Button onClick={onActivated} className="w-full bg-green-600 hover:bg-green-700">
              Continue to jobs
            </Button>
          </div>
        ) : status === "failed" ? (
          <div className="space-y-4 border-t border-primary-100 bg-red-50/40 p-5">
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button type="button" onClick={handleRetrySetup} loading={sending}>
                Retry setup
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={handleSaveManualCriteria}
                loading={savingManual}
              >
                Save manual criteria
              </Button>
            </div>
            <textarea
              value={manualCriteria}
              onChange={(e) => setManualCriteria(e.target.value)}
              rows={9}
              className="block w-full rounded-lg border border-primary-200 bg-white px-3 py-2.5 font-mono text-xs leading-relaxed text-primary-800 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
            />
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex gap-2 border-t border-primary-100 p-4">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your response…"
              disabled={sending}
              className="flex-1 rounded-lg border border-primary-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30 disabled:opacity-50"
            />
            <Button type="submit" loading={sending} disabled={!input.trim()}>
              Send
            </Button>
          </form>
        )}
      </Card>
    </div>
  );
}
