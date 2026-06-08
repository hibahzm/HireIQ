# Research: Real-Time Streaming Voice Interview (Phase 0)

All Technical Context unknowns were resolved in `/speckit-clarify` (provider, VAD placement,
barge-in scope, latency metric) and the grounding below. No open `NEEDS CLARIFICATION` remain.

## Decision 1 — Speech provider: Azure Speech (free F0 tier)

**Decision**: Use the Azure Speech SDK for both directions — streaming recognition (STT) via a
`PushAudioInputStream` + continuous recognition, and streaming synthesis (TTS) via the synthesizing
event / `AudioDataStream`. Run on the **free F0 tier** (~5 h/mo STT, 0.5M char/mo TTS).

**Rationale**: Genuinely free at this scale, real-time/streaming in both directions, and the Azure
Speech credentials are already referenced by the MVP TTS fallback — no new vendor. Critically, STT
and TTS are **separate** steps, so the existing agent graph + guardrail registry stay between them
(FR-007 / Constitution V).

**Alternatives considered**:
- *OpenAI Realtime API*: lowest latency but bundles STT+LLM+TTS into one stream, **bypassing** the
  guardrail registry and agent graph — rejected (FR-007 / Constitution V violation).
- *OpenAI Whisper + OpenAI TTS (MVP today)*: no free tier and neither streams incrementally —
  can't meet SC-001/SC-002.
- *Deepgram + ElevenLabs*: excellent streaming, but new vendors/secrets and only trial credit.

**Latent gaps closed**: `azure-cognitiveservices-speech` is **not** in `pyproject.toml`, and
`AZURE_SPEECH_KEY`/`AZURE_SPEECH_REGION` are **not** in `config.py` (the MVP `_azure_tts` fallback
references them but they don't exist). Both are added as setup tasks.

## Decision 2 — Client-side voice-activity detection

**Decision**: The browser detects end-of-speech using **silero-vad** running in **onnxruntime-web**,
fed by an AudioWorklet capture node (PCM 16 kHz mono). A sustained silence ≥ ~800 ms after speech
marks end-of-speech; brief mid-sentence pauses do not (SC-004 / FR-002).

**Rationale**: Keeps endpointing on the client (the clarified decision), gives immediate UX feedback,
and avoids streaming silence to the backend. silero-vad is small, accurate, and runs in-browser via
WASM. Reconciles the spec's AudioWorklet capture with explicit end-of-speech control.

**Alternatives considered**: server-side endpointing (Azure auto-endpointing) — rejected per the
clarification; hybrid — unnecessary complexity for V2-3.

## Decision 3 — WebSocket streaming sub-protocol

**Decision**: Extend the existing `/interviews/{token}/connect` socket with a streaming branch (used
when `session.streaming_mode` is true). New client→server messages: `audio_frame` (base64 PCM chunk,
sent continuously while the client VAD reports speech) and `end_of_speech` (control). New
server→client messages: `partial_transcript` (optional), `ai_turn_text`, `ai_audio_chunk` (base64
mp3, repeated), and `ai_audio_end`. Turn-based `text_input`/`audio_input` remain for the default and
fallback path. See [contracts/ws-streaming.md](contracts/ws-streaming.md).

**Rationale**: One socket, one auth/resume path; streaming is purely additive message types. Chunked
mp3 maps directly to the browser `MediaSource` SourceBuffer (`audio/mpeg`) so playback starts on the
first chunk (FR-004 / SC-002).

**Alternatives considered**: a second dedicated socket — rejected (duplicates auth/resume/session
wiring); WebRTC — heavyweight for a one-way-at-a-time half-duplex exchange.

## Decision 4 — Bridging the synchronous Azure Speech SDK to asyncio (Principle II)

**Decision**: The Azure Speech SDK is callback/synchronous. Wrap it so it never blocks the event
loop: push audio frames into a `PushAudioInputStream`; register `recognizing`/`recognized` (STT) and
`synthesizing` (TTS) **callbacks that enqueue onto an `asyncio.Queue`** (via
`loop.call_soon_threadsafe`); the async WS handler `await`s the queue to read finals/chunks. Any
blocking SDK call runs in a worker thread (`anyio.to_thread`).

**Rationale**: Preserves Constitution II (no sync I/O on the loop) while using a callback-based SDK.
This is the one place needing care; it adds no new architectural layer.

**Alternatives considered**: calling the SDK synchronously inside the async handler — rejected (blocks
the loop); a separate worker process — over-engineered for V2-3 scale.

## Decision 5 — Half-duplex (no barge-in) in V2-3

**Decision**: While AI audio is playing, the client suspends capture / ignores VAD; it resumes after
`ai_audio_end`. No interruption of in-flight synthesis.

**Rationale**: Clarified scope. Avoids echo-cancellation, partial-turn state, and mid-turn agent-graph
cancellation. Documented as a recommended future enhancement.

## Decision 6 — Streaming gate + fallback

**Decision**: A new `interview_sessions.streaming_mode` boolean (default false), set at session
creation from the job/session configuration (FR-005). The WS handler chooses the streaming branch only
when the flag is true **and** the streaming components initialize; on any streaming failure
(STT/TTS/SDK init, or browser capability), it falls back to the turn-based path so the interview still
completes (FR-008), within the existing 24-hour resume window.

**Rationale**: Makes streaming opt-in and safely degradable; turn-based remains the default and the
safety net with zero behavior change for existing sessions.

## Decision 7 — Transcript & evaluation parity

**Decision**: Streaming turns write to `interview_messages` with the **same** per-turn speaker
attribution and audio references as turn-based turns; the candidate utterance audio is stored exactly
as today, and the AI turn references its synthesized audio. Redis state, turn counting, completion,
and the evaluation trigger are reused unchanged.

**Rationale**: Guarantees SC-003 / FR-006 (a streamed interview is structurally indistinguishable from
a turn-based one) and keeps the downstream evaluation pipeline untouched.
