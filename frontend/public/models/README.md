# Client-side VAD model

The streaming interview uses **silero-vad** running in `onnxruntime-web` for client-side
end-of-speech detection (see `src/audio/vad.ts`).

Place the ONNX model here as:

```
frontend/public/models/silero_vad.onnx
```

Obtain it from the silero-vad project (https://github.com/snakers4/silero-vad) — the small
`silero_vad.onnx` (a few hundred KB). It is served statically at `/models/silero_vad.onnx`
and loaded by `VadEngine`. The binary is intentionally **not** committed (kept out of VCS like
other model weights, per the constitution); add it during deployment/build.
