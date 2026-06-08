// Client-side voice-activity detection for the streaming interview.
//
// `SilenceTracker` is the pure, testable end-of-speech state machine: given a per-frame
// speech/no-speech decision it reports when a sustained silence (default ≥ 800 ms) follows
// speech — so brief mid-sentence pauses do NOT end the turn (SC-004 / FR-002).
//
// `VadEngine` wraps `SilenceTracker` with silero-vad inference (onnxruntime-web) to derive
// the per-frame speech probability from audio samples.

export type VadEvent = "speech" | "silence" | "end_of_speech";

export interface SilenceTrackerOptions {
  silenceMs?: number; // sustained silence that ends a turn (default 800)
  speechThreshold?: number; // probability above which a frame counts as speech
}

export class SilenceTracker {
  private readonly silenceMs: number;
  private readonly threshold: number;
  private speechStarted = false;
  private silenceAccumMs = 0;
  private ended = false;

  constructor(opts: SilenceTrackerOptions = {}) {
    this.silenceMs = opts.silenceMs ?? 800;
    this.threshold = opts.speechThreshold ?? 0.5;
  }

  /** Feed one frame. `prob` = speech probability [0,1]; `frameMs` = frame duration. */
  update(prob: number, frameMs: number): VadEvent {
    if (this.ended) return "end_of_speech";
    const isSpeech = prob >= this.threshold;

    if (isSpeech) {
      this.speechStarted = true;
      this.silenceAccumMs = 0;
      return "speech";
    }

    // Silence — only meaningful once the candidate has actually started speaking.
    if (this.speechStarted) {
      this.silenceAccumMs += frameMs;
      if (this.silenceAccumMs >= this.silenceMs) {
        this.ended = true;
        return "end_of_speech";
      }
    }
    return "silence";
  }

  /** True once end-of-speech has fired (one-shot per utterance). */
  get hasEnded(): boolean {
    return this.ended;
  }

  reset(): void {
    this.speechStarted = false;
    this.silenceAccumMs = 0;
    this.ended = false;
  }
}

export interface VadEngineOptions extends SilenceTrackerOptions {
  modelUrl?: string;
  onEndOfSpeech: () => void;
}

/**
 * silero-vad inference over incoming frames. Loads the ONNX model lazily; on each frame it
 * computes a speech probability, feeds the SilenceTracker, and invokes `onEndOfSpeech` once
 * a sustained silence ends the turn. Inference details are intentionally thin — the model is
 * provided at `/models/silero_vad.onnx` (see public/models/README.md).
 */
export class VadEngine {
  private readonly tracker: SilenceTracker;
  private readonly modelUrl: string;
  private readonly onEnd: () => void;
  private session: unknown = null;

  constructor(opts: VadEngineOptions) {
    this.tracker = new SilenceTracker(opts);
    this.modelUrl = opts.modelUrl ?? "/models/silero_vad.onnx";
    this.onEnd = opts.onEndOfSpeech;
  }

  async init(): Promise<void> {
    const ort = await import("onnxruntime-web");
    this.session = await ort.InferenceSession.create(this.modelUrl);
  }

  /** Process one frame of mono Float32 samples (16 kHz). */
  async process(samples: Float32Array, frameMs: number): Promise<void> {
    if (this.tracker.hasEnded) return;
    const prob = await this.speechProbability(samples);
    if (this.tracker.update(prob, frameMs) === "end_of_speech") {
      this.onEnd();
    }
  }

  reset(): void {
    this.tracker.reset();
  }

  private async speechProbability(samples: Float32Array): Promise<number> {
    if (!this.session) return 0;
    const ort = await import("onnxruntime-web");
    const input = new ort.Tensor("float32", samples, [1, samples.length]);
    // silero-vad's exact I/O names/state are model-version specific; resolved at integration.
    const sess = this.session as { run: (f: Record<string, unknown>) => Promise<Record<string, { data: Float32Array }>> };
    const out = await sess.run({ input });
    const first = Object.values(out)[0];
    return first?.data?.[0] ?? 0;
  }
}
