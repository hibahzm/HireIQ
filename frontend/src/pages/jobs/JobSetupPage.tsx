import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../services/api";

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

export default function JobSetupPage({ token, jobId, onActivated, onBack }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<string>("in_progress");
  const [criteriaDraft, setCriteriaDraft] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [activating, setActivating] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Kick off the first AI turn on mount
  useEffect(() => {
    sendTurn("");
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
    } finally {
      setActivating(false);
    }
  }

  return (
    <div className="flex flex-col h-screen max-w-2xl mx-auto p-4">
      <div className="flex items-center gap-2 mb-4">
        <button onClick={onBack} className="text-gray-500 hover:text-gray-700 text-sm">
          ← Back to jobs
        </button>
        <h1 className="text-lg font-semibold text-gray-900">AI-Guided Job Setup</h1>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 pb-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg text-sm ${
                msg.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-900"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-gray-100 px-4 py-2 rounded-lg text-sm text-gray-500">
              Thinking…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && <p className="text-red-600 text-sm mb-2" role="alert">{error}</p>}

      {status === "completed" ? (
        <div className="border-t pt-4">
          <p className="text-sm text-gray-600 mb-3">
            Setup complete. Review the criteria and activate the job.
          </p>
          {criteriaDraft && (
            <pre className="bg-gray-50 p-3 rounded text-xs overflow-auto max-h-40 mb-3">
              {JSON.stringify(criteriaDraft, null, 2)}
            </pre>
          )}
          <button
            onClick={handleActivate}
            disabled={activating}
            className="w-full py-2 px-4 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50"
          >
            {activating ? "Activating…" : "Confirm & Activate Job"}
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="flex gap-2 border-t pt-4">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your response…"
            disabled={sending}
            className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 text-sm"
          >
            Send
          </button>
        </form>
      )}
    </div>
  );
}
