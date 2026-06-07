const WS_BASE = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000";

export type InboundMessage =
  | { type: "session_ready"; session_id: string; resuming: boolean; turn_count: number; max_turns: number }
  | { type: "turn_processing" }
  | { type: "ai_turn"; text: string; audio?: string }
  | { type: "turn_blocked"; message: string }
  | { type: "interview_complete" }
  | { type: "session_expired"; message: string }
  | { type: "service_error"; message: string };

export type OutboundMessage =
  | { type: "text_input"; text: string }
  | { type: "audio_input"; audio: string };

interface Callbacks {
  onReady?: (data: { resuming: boolean; turn_count: number }) => void;
  onAiTurn?: (text: string, audio?: ArrayBuffer) => void;
  onBlocked?: (message: string) => void;
  onComplete?: () => void;
  onExpired?: () => void;
  onError?: (message: string) => void;
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
          this.callbacks.onReady?.({ resuming: msg.resuming, turn_count: msg.turn_count });
          break;
        case "ai_turn": {
          let audioBuffer: ArrayBuffer | undefined;
          if (msg.audio) {
            const binary = atob(msg.audio);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
            audioBuffer = bytes.buffer;
          }
          this.callbacks.onAiTurn?.(msg.text, audioBuffer);
          break;
        }
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
    const bytes = new Uint8Array(audioBuffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
    const base64 = btoa(binary);
    this.ws?.send(JSON.stringify({ type: "audio_input", audio: base64 }));
  }

  close(): void {
    this.ws?.close();
  }
}
