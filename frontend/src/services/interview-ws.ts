// Default to a same-origin `/ws` path so the WebSocket flows through the reverse
// proxy (nginx in the container, the Vite dev-server proxy locally) rather than a
// hardcoded localhost:8000. Override with VITE_WS_URL for a different origin.
const WS_BASE =
  import.meta.env.VITE_WS_URL ??
  `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws`;

export type InboundMessage =
  | { type: "session_ready"; session_id: string; resuming: boolean; turn_count: number; max_turns: number; streaming_mode?: boolean }
  | { type: "turn_processing" }
  | { type: "ai_turn"; text: string; audio?: string }
  | { type: "partial_transcript"; text: string }
  | { type: "ai_turn_text"; text: string; counts_as_turn?: boolean }
  | { type: "ai_audio_chunk"; audio: string; seq: number }
  | { type: "ai_audio_end" }
  | { type: "turn_blocked"; message: string }
  | { type: "interview_complete" }
  | { type: "session_expired"; message: string }
  | { type: "service_error"; message: string };

export type OutboundMessage =
  | { type: "text_input"; text: string }
  | { type: "audio_input"; audio: string }
  | { type: "audio_frame"; audio: string }
  | { type: "end_of_speech" };

interface Callbacks {
  onReady?: (data: { session_id: string; resuming: boolean; turn_count: number; max_turns: number; streaming_mode: boolean }) => void;
  onProcessing?: () => void;
  onAiTurn?: (text: string, audio?: ArrayBuffer) => void;
  onPartial?: (text: string) => void;
  onAiText?: (text: string, countsAsTurn: boolean) => void;
  onAiAudioChunk?: (chunk: ArrayBuffer, seq: number) => void;
  onAiAudioEnd?: () => void;
  onBlocked?: (message: string) => void;
  onComplete?: () => void;
  onExpired?: () => void;
  onError?: (message: string) => void;
}

function b64ToArrayBuffer(b64: string): ArrayBuffer {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

export class InterviewWebSocket {
  private ws: WebSocket | null = null;
  private token: string;
  private callbacks: Callbacks;

  constructor(token: string, callbacks: Callbacks) {
    this.token = token;
    this.callbacks = callbacks;
  }

  connect(): void {
    this.ws = new WebSocket(`${WS_BASE}/interviews/${this.token}/connect`);

    this.ws.onmessage = (event) => {
      const msg: InboundMessage = JSON.parse(event.data);

      switch (msg.type) {
        case "session_ready":
          this.callbacks.onReady?.({
            session_id: msg.session_id,
            resuming: msg.resuming,
            turn_count: msg.turn_count,
            max_turns: msg.max_turns,
            streaming_mode: msg.streaming_mode ?? false,
          });
          break;
        case "turn_processing":
          this.callbacks.onProcessing?.();
          break;
        case "ai_turn": {
          const audioBuffer = msg.audio ? b64ToArrayBuffer(msg.audio) : undefined;
          this.callbacks.onAiTurn?.(msg.text, audioBuffer);
          break;
        }
        case "partial_transcript":
          this.callbacks.onPartial?.(msg.text);
          break;
        case "ai_turn_text":
          this.callbacks.onAiText?.(msg.text, msg.counts_as_turn ?? true);
          break;
        case "ai_audio_chunk":
          this.callbacks.onAiAudioChunk?.(b64ToArrayBuffer(msg.audio), msg.seq);
          break;
        case "ai_audio_end":
          this.callbacks.onAiAudioEnd?.();
          break;
        case "turn_blocked":
          this.callbacks.onBlocked?.(msg.message);
          break;
        case "interview_complete":
          this.callbacks.onComplete?.();
          break;
        case "session_expired":
          this.callbacks.onExpired?.();
          break;
        case "service_error":
          this.callbacks.onError?.(msg.message);
          break;
      }
    };

    this.ws.onerror = () => {
      this.callbacks.onError?.("Connection error");
    };
  }

  sendText(text: string): void {
    this.ws?.send(JSON.stringify({ type: "text_input", text }));
  }

  sendAudio(audioBuffer: ArrayBuffer): void {
    this.ws?.send(JSON.stringify({ type: "audio_input", audio: this.encode(audioBuffer) }));
  }

  /** Streaming: send one captured PCM16 frame while the candidate is speaking. */
  sendAudioFrame(pcmFrame: ArrayBuffer): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "audio_frame", audio: this.encode(pcmFrame) }));
    }
  }

  /** Streaming: client VAD detected end-of-speech → finalize the utterance. */
  sendEndOfSpeech(): void {
    this.ws?.send(JSON.stringify({ type: "end_of_speech" }));
  }

  private encode(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
    return btoa(binary);
  }

  close(): void {
    this.ws?.close();
  }
}
