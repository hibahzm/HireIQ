// AudioWorklet processor: emits raw mono Float32 frames from the microphone to the main
// thread. Loaded via `audioContext.audioWorklet.addModule(new URL('./capture-worklet.ts', import.meta.url))`.
//
// AudioWorklet globals are not in the standard DOM lib; declare the minimal surface so this
// module typechecks. `export {}` keeps these declarations module-local.
export {};

declare const sampleRate: number;
declare class AudioWorkletProcessor {
  readonly port: MessagePort;
  process(inputs: Float32Array[][], outputs: Float32Array[][]): boolean;
}
declare function registerProcessor(name: string, ctor: unknown): void;

class CaptureProcessor extends AudioWorkletProcessor {
  process(inputs: Float32Array[][]): boolean {
    const channel = inputs[0]?.[0];
    if (channel && channel.length) {
      // Copy out (the underlying buffer is reused by the engine each render quantum).
      this.port.postMessage({ samples: channel.slice(0), sampleRate });
    }
    return true; // keep processor alive
  }
}

registerProcessor("capture-processor", CaptureProcessor);
