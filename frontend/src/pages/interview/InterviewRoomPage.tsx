import { useEffect, useRef, useState } from "react";
import { InterviewWebSocket } from "../../services/interview-ws";
import { StreamingController } from "../../audio/streaming-controller";

interface Props {
  token: string;
}

interface Message {
  speaker: "candidate" | "ai" | "system";
  text: string;
}

export default function InterviewRoomPage({ token }: Props) {
  const [status, setStatus] = useState<"connecting" | "ready" | "complete" | "expired" | "error">("connecting");
  const [messages, setMessages] = useState<Message[]>([]);
  const [textInput, setTextInput] = useState("");
  const [useTextFallback, setUseTextFallback] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [streamingMode, setStreamingMode] = useState(false);
  const [turnCount, setTurnCount] = useState(0);
  const [maxTurns] = useState(20);
  const wsRef = useRef<InterviewWebSocket | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamingRef = useRef<StreamingController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ws = new InterviewWebSocket(token, {
      onReady: ({ resuming, turn_count, streaming_mode }) => {
        setStatus("ready");
        setTurnCount(turn_count);
        setStreamingMode(streaming_mode);
        if (resuming) {
          addMessage("system", `Resuming from turn ${turn_count}. Welcome back.`);
        }
        if (streaming_mode && audioRef.current) {
          const controller = new StreamingController(ws, audioRef.current);
          streamingRef.current = controller;
          controller.start().catch(() => {
            addMessage("system", "Couldn't start the microphone — switching to text input.");
            setUseTextFallback(true);
          });
        }
      },
      // Turn-based (full-blob) AI turn
      onAiTurn: (text, audioBuffer) => {
        setProcessing(false);
        addMessage("ai", text);
        if (audioBuffer && audioRef.current) {
          const blob = new Blob([audioBuffer], { type: "audio/mp3" });
          audioRef.current.src = URL.createObjectURL(blob);
          audioRef.current.play().catch(() => {});
        }
        setTurnCount((n) => n + 1);
      },
      // Streaming AI turn: text first, then audio chunks
      onAiText: (text) => {
        setProcessing(false);
        addMessage("ai", text);
        streamingRef.current?.beginPlayback();
        setTurnCount((n) => n + 1);
      },
      onAiAudioChunk: (chunk) => streamingRef.current?.pushChunk(chunk),
      onAiAudioEnd: () => streamingRef.current?.endPlayback(),
      onBlocked: (message) => {
        setProcessing(false);
        addMessage("system", message);
        streamingRef.current?.endPlayback(); // release half-duplex
      },
      onComplete: () => {
        setStatus("complete");
        streamingRef.current?.stop();
        addMessage("system", "Interview complete. Thank you for your time!");
      },
      onExpired: () => setStatus("expired"),
      onError: (message) => {
        setProcessing(false);
        addMessage("system", `Error: ${message}`);
      },
    });

    wsRef.current = ws;
    ws.connect();

    return () => {
      streamingRef.current?.stop();
      ws.close();
    };
  }, [token]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function addMessage(speaker: "candidate" | "ai" | "system", text: string) {
    setMessages((prev) => [...prev, { speaker, text }]);
  }

  function handleSendText(e: React.FormEvent) {
    e.preventDefault();
    const text = textInput.trim();
    if (!text || processing) return;
    setTextInput("");
    setProcessing(true);
    addMessage("candidate", text);
    wsRef.current?.sendText(text);
  }

  async function handleStartRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        const buffer = await blob.arrayBuffer();
        setProcessing(true);
        addMessage("candidate", "[Voice message]");
        wsRef.current?.sendAudio(buffer);
        stream.getTracks().forEach((t) => t.stop());
      };
      recorder.start();
      recorderRef.current = recorder;
      setIsRecording(true);
    } catch {
      addMessage("system", "Microphone access denied. Use text input instead.");
      setUseTextFallback(true);
    }
  }

  function handleStopRecording() {
    recorderRef.current?.stop();
    recorderRef.current = null;
    setIsRecording(false);
  }

  if (status === "expired") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md p-8 bg-white rounded-lg shadow text-center">
          <h1 className="text-xl font-semibold text-red-600 mb-2">Interview link expired</h1>
          <p className="text-gray-600">This interview link has expired. Please contact the recruiter for a new link.</p>
        </div>
      </div>
    );
  }

  if (status === "complete") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md p-8 bg-white rounded-lg shadow text-center">
          <div className="text-green-600 text-4xl mb-4">✓</div>
          <h1 className="text-xl font-semibold text-gray-900 mb-2">Interview complete!</h1>
          <p className="text-gray-600">Your responses have been recorded. You'll receive a feedback report via email.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen max-w-2xl mx-auto p-4">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-semibold text-gray-900">AI Interview</h1>
        <div className="text-sm text-gray-500">
          Turn {turnCount} of {maxTurns}
        </div>
      </div>

      <audio ref={audioRef} className="hidden" />

      <div className="flex-1 overflow-y-auto space-y-3 pb-4">
        {status === "connecting" && (
          <div className="text-center text-gray-500 py-8">Connecting to interview session…</div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.speaker === "candidate" ? "justify-end" : msg.speaker === "system" ? "justify-center" : "justify-start"}`}
          >
            <div
              className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg text-sm ${
                msg.speaker === "candidate"
                  ? "bg-blue-600 text-white"
                  : msg.speaker === "system"
                  ? "bg-yellow-50 text-yellow-800 text-xs italic"
                  : "bg-gray-100 text-gray-900"
              }`}
            >
              {msg.text}
            </div>
          </div>
        ))}
        {processing && (
          <div className="flex justify-start">
            <div className="bg-gray-100 px-4 py-2 rounded-lg text-sm text-gray-500 animate-pulse">
              AI is thinking…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {status === "ready" && (
        <div className="border-t pt-4">
          <div className="flex items-center gap-2 mb-2">
            <button
              onClick={() => setUseTextFallback(!useTextFallback)}
              className="text-xs text-gray-500 hover:text-gray-700"
            >
              {useTextFallback ? "Switch to voice" : "Switch to text"}
            </button>
          </div>

          {useTextFallback ? (
            <form onSubmit={handleSendText} className="flex gap-2">
              <input
                type="text"
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                placeholder="Type your response…"
                disabled={processing}
                className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={processing || !textInput.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 text-sm"
              >
                Send
              </button>
            </form>
          ) : streamingMode ? (
            <div className="flex justify-center" aria-live="polite">
              <div className="px-6 py-3 bg-gray-100 text-gray-700 rounded-full flex items-center gap-2 text-sm">
                <span className="w-2.5 h-2.5 bg-green-500 rounded-full animate-pulse" />
                {processing ? "Thinking…" : "Listening — just speak naturally"}
              </div>
            </div>
          ) : (
            <div className="flex justify-center">
              {isRecording ? (
                <button
                  onClick={handleStopRecording}
                  className="px-6 py-3 bg-red-600 text-white rounded-full hover:bg-red-700 flex items-center gap-2"
                >
                  <span className="w-3 h-3 bg-white rounded-full animate-pulse" />
                  Stop recording
                </button>
              ) : (
                <button
                  onClick={handleStartRecording}
                  disabled={processing}
                  className="px-6 py-3 bg-blue-600 text-white rounded-full hover:bg-blue-700 disabled:opacity-50"
                >
                  Hold to record
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
