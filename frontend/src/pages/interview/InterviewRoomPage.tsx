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
  const [started, setStarted] = useState(false);
  const [status, setStatus] = useState<"idle" | "connecting" | "ready" | "complete" | "expired" | "error">("idle");
  const [messages, setMessages] = useState<Message[]>([]);
  const [processing, setProcessing] = useState(false);
  const [aiSpeaking, setAiSpeaking] = useState(false);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [voiceUnavailable, setVoiceUnavailable] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [streamingMode, setStreamingMode] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [turnCount, setTurnCount] = useState(0);
  const [maxTurns, setMaxTurns] = useState(20);
  const wsRef = useRef<InterviewWebSocket | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamingRef = useRef<StreamingController | null>(null);
  const audioBlockShownRef = useRef(false);
  const streamingModeRef = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!started) return;

    const ws = new InterviewWebSocket(token, {
      onReady: ({ session_id, resuming, turn_count, max_turns, streaming_mode }) => {
        setStatus("ready");
        setSessionId(session_id);
        setTurnCount(turn_count);
        setMaxTurns(max_turns);
        setStreamingMode(streaming_mode);
        if (resuming) {
          addMessage("system", `Resuming from turn ${turn_count}. Welcome back.`);
        }
        if (streaming_mode) {
          void startStreamingVoice(ws);
        }
      },
      onProcessing: () => {
        setProcessing(true);
        setAiSpeaking(false);
        if (streamingModeRef.current) {
          addMessage("candidate", "[Voice response]");
        }
      },
      // Turn-based (full-blob) AI turn
      onAiTurn: (text, audioBuffer) => {
        setProcessing(false);
        setAiSpeaking(false);
        addMessage("ai", text);
        if (audioBuffer && audioRef.current) {
          const blob = new Blob([audioBuffer], { type: "audio/mp3" });
          audioRef.current.src = URL.createObjectURL(blob);
          audioRef.current.play().catch(() => {});
        }
        setTurnCount((n) => n + 1);
      },
      // Streaming AI turn: text first, then audio chunks
      onAiText: (text, countsAsTurn) => {
        setProcessing(false);
        setAiSpeaking(true);
        addMessage("ai", text);
        streamingRef.current?.beginPlayback();
        if (countsAsTurn) {
          setTurnCount((n) => n + 1);
        }
      },
      onAiAudioChunk: (chunk) => streamingRef.current?.pushChunk(chunk),
      onAiAudioEnd: () => {
        setAiSpeaking(false);
        streamingRef.current?.endPlayback();
      },
      onBlocked: (message) => {
        setProcessing(false);
        setAiSpeaking(false);
        addMessage("system", message);
        streamingRef.current?.endPlayback(); // release half-duplex
      },
      onComplete: () => {
        setStatus("complete");
        setAiSpeaking(false);
        streamingRef.current?.stop();
        addMessage("system", "Interview complete. Thank you for your time!");
      },
      onExpired: () => {
        setAiSpeaking(false);
        setStatus("expired");
      },
      onError: (message) => {
        setProcessing(false);
        setAiSpeaking(false);
        addMessage("system", `Error: ${message}`);
      },
    });

    wsRef.current = ws;
    ws.connect();

    return () => {
      streamingRef.current?.stop();
      ws.close();
    };
  }, [token, started]);

  useEffect(() => {
    streamingModeRef.current = streamingMode;
  }, [streamingMode]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function addMessage(speaker: "candidate" | "ai" | "system", text: string) {
    setMessages((prev) => [...prev, { speaker, text }]);
  }

  function handleStartInterview() {
    setStatus("connecting");
    setStarted(true);
  }

  async function handleEnableAudio() {
    try {
      await audioRef.current?.play();
      setAudioBlocked(false);
    } catch {
      setAudioBlocked(true);
    }
  }

  async function startStreamingVoice(ws = wsRef.current) {
    if (!ws || !audioRef.current) return;

    streamingRef.current?.stop();
    const controller = new StreamingController(ws, audioRef.current, {
      onPlaybackBlocked: () => {
        setAudioBlocked(true);
        if (!audioBlockShownRef.current) {
          audioBlockShownRef.current = true;
          addMessage("system", "Audio playback is blocked. Use Enable audio to hear the interviewer.");
        }
      },
    });
    streamingRef.current = controller;

    try {
      await controller.start();
      setVoiceUnavailable(false);
    } catch (err) {
      console.error("interview.streaming_start_failed", err);
      const reason = err instanceof Error && err.message ? ` (${err.message})` : "";
      setAiSpeaking(false);
      addMessage("system", `Couldn't start the microphone${reason}. Microphone access is required for this interview.`);
      streamingRef.current = null;
      setVoiceUnavailable(true);
    }
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
      addMessage("system", "Microphone access denied. Microphone access is required for this interview.");
    }
  }

  function handleStopRecording() {
    recorderRef.current?.stop();
    recorderRef.current = null;
    setIsRecording(false);
  }

  const streamingStatusText = aiSpeaking
    ? "AI is speaking..."
    : processing
      ? "Thinking..."
      : voiceUnavailable
        ? "Microphone unavailable"
      : "Listening - just speak naturally";
  const streamingDotClass = voiceUnavailable
    ? "bg-red-500"
    : aiSpeaking
      ? "bg-blue-500"
      : processing
        ? "bg-amber-500"
        : "bg-green-500";

  if (status === "idle") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div className="max-w-md w-full p-8 bg-white rounded-lg shadow text-center">
          <h1 className="text-xl font-semibold text-gray-900 mb-2">AI Interview</h1>
          <p className="text-gray-600 mb-6">Ready when you are.</p>
          <button
            onClick={handleStartInterview}
            className="px-5 py-2.5 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm font-medium"
          >
            Start interview
          </button>
        </div>
      </div>
    );
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
        <div className="text-right text-sm text-gray-500">
          {sessionId && <div className="font-mono text-xs">Session {sessionId.slice(0, 8)}</div>}
          <div>Turn {turnCount} of {maxTurns}</div>
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
            {audioBlocked && (
              <button
                onClick={handleEnableAudio}
                className="text-xs text-blue-600 hover:text-blue-700"
              >
                Enable audio
              </button>
            )}
          </div>

          {streamingMode ? (
            <div className="flex justify-center" aria-live="polite">
              <div className="px-6 py-3 bg-gray-100 text-gray-700 rounded-full flex items-center gap-2 text-sm">
                <span className={`w-2.5 h-2.5 ${streamingDotClass} rounded-full animate-pulse`} />
                {streamingStatusText}
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
                  Start recording
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
