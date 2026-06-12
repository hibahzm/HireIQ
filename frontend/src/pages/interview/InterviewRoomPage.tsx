import { useEffect, useRef, useState } from "react";
import { InterviewWebSocket } from "../../services/interview-ws";
import { StreamingController } from "../../audio/streaming-controller";
import AiAvatar, { type AvatarState } from "../../components/ui/AiAvatar";
import Logo from "../../components/ui/Logo";

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
  const [candidateSpeaking, setCandidateSpeaking] = useState(false);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [voiceUnavailable, setVoiceUnavailable] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [streamingMode, setStreamingMode] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [turnCount, setTurnCount] = useState(0);
  const [maxTurns, setMaxTurns] = useState(20);
  const [showTranscript, setShowTranscript] = useState(false);
  const wsRef = useRef<InterviewWebSocket | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamingRef = useRef<StreamingController | null>(null);
  const audioBlockShownRef = useRef(false);
  const aiSpeakingRef = useRef(false);
  // True from "AI turn text received" until its streamed audio fully played out;
  // gates interview completion so the closing line isn't cut off.
  const playbackPendingRef = useRef(false);
  const pendingCompleteRef = useRef(false);
  const completionShownRef = useRef(false);
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
      onHistory: (history) => {
        setMessages(history);
      },
      onProcessing: () => {
        setProcessing(true);
        setCandidateSpeaking(false);
        aiSpeakingRef.current = false;
        setAiSpeaking(false);
      },
      onPartial: (text) => {
        setCandidateSpeaking(false);
        addMessage("candidate", text);
      },
      // Turn-based (full-blob) AI turn. The avatar's "speaking" state is driven by
      // the <audio> element's playing/ended events so the mouth moves with the sound.
      onAiTurn: (text, audioBuffer) => {
        setProcessing(false);
        addMessage("ai", text);
        if (audioBuffer && audioRef.current) {
          const blob = new Blob([audioBuffer], { type: "audio/mp3" });
          audioRef.current.src = URL.createObjectURL(blob);
          audioRef.current.play().catch(() => {
            setAudioBlocked(true);
          });
        }
        setTurnCount((n) => n + 1);
      },
      // Streaming AI turn: text first, then audio chunks
      onAiText: (text, countsAsTurn, append) => {
        setProcessing(false);
        playbackPendingRef.current = true;
        if (append) {
          addMessage("ai", text);
        }
        streamingRef.current?.beginPlayback();
        if (countsAsTurn) {
          setTurnCount((n) => n + 1);
        }
      },
      onAiAudioChunk: (chunk) => streamingRef.current?.pushChunk(chunk),
      onAiAudioEnd: () => {
        streamingRef.current?.endPlayback();
      },
      onBlocked: (message) => {
        setProcessing(false);
        setCandidateSpeaking(false);
        aiSpeakingRef.current = false;
        setAiSpeaking(false);
        addMessage("system", message);
        streamingRef.current?.endPlayback(); // release half-duplex
      },
      onComplete: () => {
        pendingCompleteRef.current = true;
        const el = audioRef.current;
        const audioActive =
          playbackPendingRef.current || (el ? !el.paused && !el.ended : false);
        if (!audioActive) {
          finishInterview();
        }
      },
      onExpired: () => {
        aiSpeakingRef.current = false;
        setAiSpeaking(false);
        setStatus("expired");
      },
      onError: (message) => {
        setProcessing(false);
        aiSpeakingRef.current = false;
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
    aiSpeakingRef.current = aiSpeaking;
  }, [aiSpeaking]);

  // Drive the avatar's mouth from the audio element itself: it animates exactly
  // while sound is coming out, not from when the text message arrived.
  useEffect(() => {
    if (!started) return;
    const el = audioRef.current;
    if (!el) return;
    const onPlaying = () => {
      aiSpeakingRef.current = true;
      setAiSpeaking(true);
    };
    const onStopped = () => {
      aiSpeakingRef.current = false;
      setAiSpeaking(false);
      if (pendingCompleteRef.current && !playbackPendingRef.current) {
        finishInterview();
      }
    };
    el.addEventListener("playing", onPlaying);
    el.addEventListener("pause", onStopped);
    el.addEventListener("ended", onStopped);
    return () => {
      el.removeEventListener("playing", onPlaying);
      el.removeEventListener("pause", onStopped);
      el.removeEventListener("ended", onStopped);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [started]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, showTranscript]);

  function addMessage(speaker: "candidate" | "ai" | "system", text: string) {
    setMessages((prev) => [...prev, { speaker, text }]);
  }

  function finishInterview() {
    if (completionShownRef.current) return;
    completionShownRef.current = true;
    pendingCompleteRef.current = false;
    playbackPendingRef.current = false;
    aiSpeakingRef.current = false;
    setProcessing(false);
    setAiSpeaking(false);
    setCandidateSpeaking(false);
    setStatus("complete");
    streamingRef.current?.stop();
    addMessage("system", "Interview complete. Thank you for your time!");
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
          addMessage("system", "Audio playback is blocked. Use Enable audio to hear Sila.");
        }
      },
      onPlaybackComplete: () => {
        playbackPendingRef.current = false;
        aiSpeakingRef.current = false;
        setAiSpeaking(false);
        if (pendingCompleteRef.current) {
          finishInterview();
        }
      },
      onSpeechStart: () => setCandidateSpeaking(true),
      onSpeechEnd: () => setCandidateSpeaking(false),
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
    ? "Sila is speaking…"
    : processing
      ? "Sila is thinking…"
      : voiceUnavailable
        ? "Microphone unavailable"
        : candidateSpeaking
          ? "Recording your answer — pause when you're done"
          : "Listening — just speak naturally";
  const streamingDotClass = voiceUnavailable
    ? "bg-red-500"
    : aiSpeaking
      ? "bg-brand-400"
      : processing
        ? "bg-amber-400"
        : candidateSpeaking
          ? "bg-red-400"
          : "bg-emerald-400";

  const avatarState: AvatarState = aiSpeaking
    ? "speaking"
    : processing
      ? "thinking"
      : status === "ready" && streamingMode && !voiceUnavailable
        ? "listening"
        : "idle";

  // Full-screen dark stage shared by the pre-start / expired / complete views.
  // Layered navy gradient + glows so it reads as a designed scene, not a black screen.
  const stage = (content: React.ReactNode) => (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-gradient-to-b from-primary-600 via-primary-700 to-primary-800 px-4 py-10">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-24 left-1/2 h-[28rem] w-[44rem] -translate-x-1/2 rounded-full bg-brand-500/25 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute bottom-[-8rem] left-[-8rem] h-80 w-80 rounded-full bg-brand-600/20 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute bottom-[-6rem] right-[-6rem] h-72 w-72 rounded-full bg-emerald-500/10 blur-3xl"
      />
      {/* Subtle dot grid for texture */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.12]"
        style={{
          backgroundImage: "radial-gradient(circle, #94a3b8 1px, transparent 1px)",
          backgroundSize: "28px 28px",
        }}
      />
      <div className="absolute top-6 left-1/2 -translate-x-1/2">
        <Logo size={32} onDark />
      </div>
      <div className="relative flex w-full max-w-md flex-col items-center text-center">{content}</div>
    </div>
  );

  if (status === "idle") {
    return stage(
      <>
        <div className="animate-scale-in">
          <AiAvatar state="idle" size={150} />
        </div>
        <h1 className="mt-6 animate-fade-in-up text-2xl font-bold text-white" style={{ animationDelay: "100ms" }}>
          Meet Sila, your AI interviewer
        </h1>
        <p className="mt-3 animate-fade-in-up text-sm leading-relaxed text-primary-100" style={{ animationDelay: "200ms" }}>
          You'll have a natural voice conversation with Sila. Find a quiet spot and make sure
          your microphone is ready.
        </p>
        <button
          onClick={handleStartInterview}
          className="mt-8 animate-fade-in-up rounded-full bg-brand-500 px-8 py-3.5 text-sm font-semibold text-white shadow-lg shadow-brand-500/30 transition-all duration-150 hover:bg-brand-400 hover:shadow-brand-400/40 active:scale-[0.97] cursor-pointer"
          style={{ animationDelay: "300ms" }}
        >
          Start interview
        </button>
        <p className="mt-4 animate-fade-in text-xs text-primary-200" style={{ animationDelay: "450ms" }}>
          Microphone access will be requested when the interview begins.
        </p>
      </>
    );
  }

  if (status === "expired") {
    return stage(
      <>
        <div className="animate-scale-in">
          <AiAvatar state="idle" size={120} />
        </div>
        <h1 className="mt-6 text-xl font-bold text-white">This interview link has expired</h1>
        <p className="mt-2 text-sm text-primary-100">
          Please contact the recruiter to request a new link.
        </p>
      </>
    );
  }

  if (status === "complete") {
    return stage(
      <>
        <span className="flex h-20 w-20 animate-scale-in items-center justify-center rounded-full bg-emerald-500/15 ring-2 ring-emerald-400/50">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#34d399" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </span>
        <h1 className="mt-6 animate-fade-in-up text-2xl font-bold text-white" style={{ animationDelay: "100ms" }}>
          Interview complete!
        </h1>
        <p className="mt-3 animate-fade-in-up text-sm leading-relaxed text-primary-100" style={{ animationDelay: "200ms" }}>
          Your responses have been recorded. You'll receive a feedback report via email.
        </p>
      </>
    );
  }

  const progress = maxTurns > 0 ? Math.min((turnCount / maxTurns) * 100, 100) : 0;

  // Voice-first view: surface only Sila's latest line as a subtitle, plus the
  // most recent system notice (if it is the newest message).
  const lastAiText = [...messages].reverse().find((m) => m.speaker === "ai")?.text ?? "";
  const lastMessage = messages[messages.length - 1];
  const lastSystemText = lastMessage?.speaker === "system" ? lastMessage.text : null;

  return (
    <div className="flex h-screen flex-col bg-gradient-to-b from-primary-600 via-primary-700 to-primary-800">
      {/* Header: brand + turn progress */}
      <header className="flex items-center justify-between px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <Logo size={28} onDark />
          <span className="hidden text-xs font-medium text-primary-200 sm:inline">
            Interview with Sila
          </span>
        </div>
        <div className="text-right">
          {sessionId && (
            <div className="font-mono text-[10px] text-primary-300">Session {sessionId.slice(0, 8)}</div>
          )}
          <div className="text-xs font-medium text-primary-100">
            Turn {turnCount} of {maxTurns}
          </div>
        </div>
      </header>
      <div className="mx-4 h-1 overflow-hidden rounded-full bg-primary-800/60 sm:mx-6" aria-hidden="true">
        <div
          className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-400 transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>

      <audio ref={audioRef} className="hidden" />

      {/* Voice-first stage: Sila is the focus; her words appear as subtitles. */}
      <main className="relative flex flex-1 flex-col items-center justify-center overflow-hidden px-4">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute top-1/4 left-1/2 h-72 w-[34rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-brand-500/15 blur-3xl"
        />
        <div className="animate-scale-in">
          <AiAvatar state={avatarState} size={160} />
        </div>
        <div className="mt-4 flex items-center gap-2 text-sm text-primary-100" aria-live="polite">
          <span className={`h-2 w-2 rounded-full ${streamingDotClass} animate-pulse`} />
          {status === "connecting" ? "Connecting to interview session…" : streamingStatusText}
        </div>

        {/* Subtitles: the current question/remark, so candidates can re-read it */}
        <div className="mt-6 min-h-[5rem] w-full max-w-xl text-center" aria-live="polite">
          {lastAiText && (
            <p
              key={lastAiText}
              className="animate-fade-in-up text-lg font-medium leading-relaxed text-white"
            >
              {lastAiText}
            </p>
          )}
          {lastSystemText && (
            <p className="mx-auto mt-3 max-w-md animate-fade-in rounded-full bg-amber-500/15 px-4 py-1.5 text-xs italic text-amber-200 ring-1 ring-amber-400/30">
              {lastSystemText}
            </p>
          )}
        </div>
      </main>

      {/* Bottom controls */}
      <div className="flex flex-col items-center gap-3 px-4 pb-5">
        {audioBlocked && status === "ready" && (
          <button
            onClick={handleEnableAudio}
            className="rounded-full bg-white/10 px-5 py-2 text-xs font-semibold text-white ring-1 ring-white/25 transition-colors duration-150 hover:bg-white/20 cursor-pointer"
          >
            Enable audio to hear Sila
          </button>
        )}

        {status === "ready" && !streamingMode && (
          <div className="flex justify-center">
            {isRecording ? (
              <button
                onClick={handleStopRecording}
                className="flex items-center gap-2 rounded-full bg-red-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-red-600/25 transition-all duration-150 hover:bg-red-700 active:scale-[0.97] cursor-pointer"
              >
                <span className="h-3 w-3 animate-pulse rounded-full bg-white" />
                Stop recording
              </button>
            ) : (
              <button
                onClick={handleStartRecording}
                disabled={processing}
                className="rounded-full bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-brand-600/25 transition-all duration-150 hover:bg-brand-700 active:scale-[0.97] disabled:opacity-50 disabled:active:scale-100 cursor-pointer"
              >
                Start recording
              </button>
            )}
          </div>
        )}

        <button
          onClick={() => setShowTranscript((v) => !v)}
          aria-expanded={showTranscript}
          className="text-xs font-medium text-primary-200 underline-offset-4 transition-colors duration-150 hover:text-white hover:underline cursor-pointer"
        >
          {showTranscript ? "Hide transcript" : "Show transcript"}
        </button>
      </div>

      {/* Collapsible transcript (accessibility + re-reading past turns) */}
      {showTranscript && (
        <div className="fixed inset-x-0 bottom-0 z-20 mx-auto flex max-h-[55vh] w-full max-w-2xl animate-fade-in-up flex-col overflow-hidden rounded-t-3xl bg-canvas shadow-2xl">
          <div className="flex items-center justify-between border-b border-primary-100 px-5 py-3">
            <span className="text-sm font-semibold text-primary-800">Transcript</span>
            <button
              onClick={() => setShowTranscript(false)}
              aria-label="Close transcript"
              className="rounded-full px-2 py-1 text-sm text-primary-400 transition-colors duration-150 hover:bg-primary-50 hover:text-primary-700 cursor-pointer"
            >
              ✕
            </button>
          </div>
          <div className="flex-1 space-y-3 overflow-y-auto p-4 sm:p-6">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex animate-fade-in-up items-end gap-2 ${
                  msg.speaker === "candidate"
                    ? "justify-end"
                    : msg.speaker === "system"
                      ? "justify-center"
                      : "justify-start"
                }`}
              >
                {msg.speaker === "ai" && (
                  <span className="mb-0.5 shrink-0">
                    <AiAvatar state="idle" size={30} />
                  </span>
                )}
                <div
                  className={`max-w-xs rounded-2xl px-4 py-2.5 text-sm lg:max-w-md ${
                    msg.speaker === "candidate"
                      ? "rounded-br-md bg-brand-600 text-white shadow-sm"
                      : msg.speaker === "system"
                        ? "bg-amber-50 text-xs italic text-amber-800 ring-1 ring-amber-200"
                        : "rounded-bl-md bg-white text-primary-700 shadow-card ring-1 ring-primary-100"
                  }`}
                >
                  {msg.text}
                </div>
              </div>
            ))}
            {processing && (
              <div className="flex animate-fade-in items-end gap-2">
                <span className="mb-0.5 shrink-0">
                  <AiAvatar state="thinking" size={30} />
                </span>
                <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-md bg-white px-4 py-3 shadow-card ring-1 ring-primary-100">
                  {[0, 150, 300].map((delay) => (
                    <span
                      key={delay}
                      className="h-1.5 w-1.5 animate-dot-bounce rounded-full bg-primary-400"
                      style={{ animationDelay: `${delay}ms` }}
                    />
                  ))}
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>
      )}
    </div>
  );
}
