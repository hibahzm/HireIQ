// Orchestrates the browser side of a streaming voice interview:
//  - continuous mic capture via an AudioWorklet (no record/stop button)
//  - client-side energy VAD → end-of-speech
//  - downsample to PCM16 16 kHz frames streamed over the WebSocket
//  - chunked AI audio playback via MediaSource (starts on first chunk)
//  - half-duplex: capture is suspended while the AI is speaking (no barge-in in V2-3)
//
// This module is browser-only and is not exercised by unit tests. The pure
// end-of-speech state machine lives in SilenceTracker / vad.ts, which is tested.

import { SilenceTracker } from "./vad";
import type { InterviewWebSocket } from "../services/interview-ws";

const TARGET_RATE = 16000;
const END_OF_SPEECH_SILENCE_MS = 1200;
const MIN_ENERGY_SPEECH_THRESHOLD = 0.015;
const CAPTURE_PROCESSOR_NAME = "capture-processor";
const CAPTURE_WORKLET_SOURCE = `
class CaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) {
      this.port.postMessage({ samples: channel.slice(0), sampleRate });
    }
    return true;
  }
}

registerProcessor("${CAPTURE_PROCESSOR_NAME}", CaptureProcessor);
`;

interface StreamingControllerOptions {
  onPlaybackBlocked?: () => void;
}

export class StreamingController {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private readonly speechTracker = new SilenceTracker({
    silenceMs: END_OF_SPEECH_SILENCE_MS,
    speechThreshold: 0.5,
  });
  private noiseFloor = 0.006;
  private speaking = false; // AI is playing → suspend capture (half-duplex)
  private capturing = false;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private captureNode: AudioNode | null = null;
  private silentGain: GainNode | null = null;

  // Playback
  private mediaSource: MediaSource | null = null;
  private sourceBuffer: SourceBuffer | null = null;
  private pending: ArrayBuffer[] = [];

  constructor(
    private readonly ws: InterviewWebSocket,
    private readonly audioEl: HTMLAudioElement,
    private readonly options: StreamingControllerOptions = {},
  ) {}

  /** Start continuous capture + VAD. Resolves once the mic + worklet are live. */
  async start(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("This browser cannot access a microphone on the current page.");
    }

    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.ctx = new AudioContext();
    if (this.ctx.state === "suspended") {
      await this.ctx.resume().catch(() => {});
    }

    this.sourceNode = this.ctx.createMediaStreamSource(this.stream);
    this.silentGain = this.ctx.createGain();
    this.silentGain.gain.value = 0;
    this.silentGain.connect(this.ctx.destination);

    try {
      await this.startAudioWorkletCapture();
    } catch {
      this.startScriptProcessorCapture();
    }

    this.capturing = true;
  }

  private async startAudioWorkletCapture(): Promise<void> {
    if (!this.ctx?.audioWorklet || !this.sourceNode || !this.silentGain) {
      throw new Error("AudioWorklet is not available.");
    }

    const blobUrl = URL.createObjectURL(
      new Blob([CAPTURE_WORKLET_SOURCE], { type: "application/javascript" }),
    );
    try {
      await this.ctx.audioWorklet.addModule(blobUrl);
    } finally {
      URL.revokeObjectURL(blobUrl);
    }

    const node = new AudioWorkletNode(this.ctx, CAPTURE_PROCESSOR_NAME);
    node.port.onmessage = (ev: MessageEvent) => {
      const { samples, sampleRate } = ev.data as { samples: Float32Array; sampleRate: number };
      this.handleSamples(samples, sampleRate);
    };

    this.sourceNode.connect(node);
    node.connect(this.silentGain);
    this.captureNode = node;
  }

  private startScriptProcessorCapture(): void {
    if (!this.ctx || !this.sourceNode || !this.silentGain) {
      throw new Error("Audio capture could not be initialized.");
    }

    const node = this.ctx.createScriptProcessor(2048, 1, 1);
    node.onaudioprocess = (ev) => {
      const samples = ev.inputBuffer.getChannelData(0).slice(0);
      this.handleSamples(samples, this.ctx?.sampleRate ?? ev.inputBuffer.sampleRate);
    };

    this.sourceNode.connect(node);
    node.connect(this.silentGain);
    this.captureNode = node;
  }

  private handleSamples(samples: Float32Array, sampleRate: number): void {
    if (!this.capturing || this.speaking) return;
    const pcm16 = downsampleToPcm16(samples, sampleRate, TARGET_RATE);
    this.ws.sendAudioFrame(pcm16.buffer as ArrayBuffer);

    const frameMs = Math.max(1, (samples.length / sampleRate) * 1000);
    if (this.speechTracker.update(this.energySpeechProbability(samples), frameMs) === "end_of_speech") {
      this.handleEndOfSpeech();
    }
  }

  private energySpeechProbability(samples: Float32Array): number {
    let sumSquares = 0;
    for (let i = 0; i < samples.length; i++) {
      sumSquares += samples[i] * samples[i];
    }
    const rms = Math.sqrt(sumSquares / Math.max(1, samples.length));
    const threshold = Math.max(MIN_ENERGY_SPEECH_THRESHOLD, this.noiseFloor * 3);

    if (rms < threshold) {
      this.noiseFloor = this.noiseFloor * 0.98 + rms * 0.02;
    }

    return rms >= threshold ? 1 : 0;
  }

  private handleEndOfSpeech(): void {
    if (!this.capturing || this.speaking) return;
    this.ws.sendEndOfSpeech();
    // Enter half-duplex until the AI finishes speaking.
    this.speaking = true;
    this.speechTracker.reset();
  }

  // ── AI audio playback (MediaSource chunked) ──────────────────────────────
  beginPlayback(): void {
    this.speaking = true;
    this.pending = [];
    this.mediaSource = new MediaSource();
    this.audioEl.src = URL.createObjectURL(this.mediaSource);
    this.mediaSource.addEventListener("sourceopen", () => {
      if (!this.mediaSource) return;
      this.sourceBuffer = this.mediaSource.addSourceBuffer("audio/mpeg");
      this.sourceBuffer.addEventListener("updateend", () => this.flush());
      this.flush();
    });
    this.audioEl.play().catch(() => {
      this.options.onPlaybackBlocked?.();
    });
  }

  pushChunk(chunk: ArrayBuffer): void {
    this.pending.push(chunk);
    this.flush();
  }

  private flush(): void {
    if (!this.sourceBuffer || this.sourceBuffer.updating) return;
    const next = this.pending.shift();
    if (next) this.sourceBuffer.appendBuffer(new Uint8Array(next));
  }

  endPlayback(): void {
    try {
      if (this.mediaSource && this.mediaSource.readyState === "open" && this.sourceBuffer && !this.sourceBuffer.updating) {
        this.mediaSource.endOfStream();
      }
    } catch {
      /* ignore */
    }
    // Resume capturing for the next candidate turn (half-duplex release).
    this.speaking = false;
    this.speechTracker.reset();
  }

  stop(): void {
    this.capturing = false;
    this.speaking = false;
    this.speechTracker.reset();
    this.audioEl.pause();
    this.audioEl.removeAttribute("src");
    this.audioEl.load();
    this.captureNode?.disconnect();
    this.sourceNode?.disconnect();
    this.silentGain?.disconnect();
    this.captureNode = null;
    this.sourceNode = null;
    this.silentGain = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close();
    this.stream = null;
    this.ctx = null;
  }
}

/** Naive linear-decimation downsample of mono Float32 → Int16 PCM at the target rate. */
function downsampleToPcm16(input: Float32Array, inRate: number, outRate: number): Int16Array {
  if (outRate >= inRate) {
    return floatToPcm16(input);
  }
  const ratio = inRate / outRate;
  const outLen = Math.floor(input.length / ratio);
  const out = new Int16Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const s = Math.max(-1, Math.min(1, input[Math.floor(i * ratio)]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

function floatToPcm16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}
