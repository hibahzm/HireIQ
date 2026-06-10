import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../services/api";
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
  const bottomRef = useRef<HTMLDivElement>(null);

  // Kick off the first AI turn on mount. The backend seeds this turn with the
  // recruiter-provided job description, so the assistant opens by reflecting
  // what it already extracted and asking only about gaps.
  useEffect(() => {
    sendTurn("");
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
      setStatus(res.status);
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
      onActivated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Activation failed");
      setActivating(false);
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
            <Button onClick={handleActivate} loading={activating} className="w-full bg-green-600 hover:bg-green-700">
              Confirm &amp; activate job
            </Button>
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
