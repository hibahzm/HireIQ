# Implementation Plan: Real-Time Streaming Voice Interview

**Branch**: `017-video-interview` | **Date**: 2026-06-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/017-video-interview/spec.md`

---

## Summary

Add a **streaming voice mode** to the existing WebSocket interview so a candidate speaks
continuously (no record/stop button), end-of-speech is detected **client-side** (silero-vad
via onnxruntime-web over AudioWorklet capture), audio is recognized incrementally on the
backend via **Azure Speech streaming STT (free F0 tier)**, the existing agent graph +
guardrail registry produce the reply, and **Azure Speech streaming TTS** sends audio back in
chunks so playback starts before synthesis finishes. Streaming is gated per session by a new
`interview_sessions.streaming_mode` flag (default off); when off or on any streaming failure,
the system uses the **unchanged turn-based path** (FR-005/FR-008). Transcript storage,
guardrails, Redis session state, the 24-hour resume window, and evaluation triggering are all
reused unchanged, so a streamed interview is indistinguishable downstream from a turn-based one.
Barge-in is out of scope for V2-3 (half-duplex). This feature also closes two latent MVP gaps:
the `azure-cognitiveservices-speech` dependency and the `AZURE_SPEECH_KEY`/`AZURE_SPEECH_REGION`
settings (referenced by the existing TTS fallback but currently undeclared).

---

## Technical Context

**Language/Version**: Python 3.12 (backend), Node 20 / TypeScript 5 (frontend)

**Primary Dependencies**: FastAPI WebSockets, existing `InterviewService` / agents `interview/turn`
(guardrails), Redis session state. **Adds** `azure-cognitiveservices-speech` (backend streaming
STT+TTS) and `onnxruntime-web` + a bundled silero-vad ONNX model (frontend client-side VAD).

**Storage**: PostgreSQL with RLS. **One additive migration**: `interview_sessions.streaming_mode
BOOLEAN NOT NULL DEFAULT false`. Transcript (`interview_messages`) and audio-blob storage are
unchanged (FR-006).

**Testing**: `pytest` + `pytest-asyncio` (backend), Vitest (frontend). Voice interview turn
handling is a **Constitution-VIII TDD-mandated domain**, so streaming input / turn-sequencing /
output tests are written failing-first and are gating.

**Target Platform**: Docker Compose (dev) / Azure Container Apps (prod) — unchanged.

**Project Type**: Multi-service web app (backend + agents + frontend) — unchanged.

**Performance Goals**: end-of-speech → first AI audio chunk **p95 ≤ 2 s**, tracked (SC-001);
playback begins before synthesis completes (SC-002).

**Constraints**: guardrails MUST run between transcript and AI response (FR-007); half-duplex
(no barge-in) in V2-3; English only; Azure Speech SDK is callback/synchronous and MUST be bridged
to asyncio without blocking the event loop (Principle II — see research.md Decision 4).

**Scale/Scope**: One streaming branch in the interview WS, two backend streaming services, one
column, frontend capture/VAD/playback. Free-tier Azure Speech (F0): ~5 h/mo STT, 0.5M char/mo TTS.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. User-First Design | ✅ PASS | Natural streaming conversation (US1); text fallback retained (FR), WCAG 2.1 AA controls preserved. |
| II. Async-First Python | ⚠️ PASS w/ care | Azure Speech SDK is callback/synchronous; it is wrapped so recognition/synthesis run off the event loop and surface results via an `asyncio.Queue` (research Decision 4). No sync calls block the loop. |
| III. Clean Architecture | ✅ PASS | New `StreamingSttService` / `StreamingTtsService` hold the speech logic; `InterviewService` keeps the turn-core (history → agents/guardrails → persist); the WS router stays a thin transport adapter. |
| IV. Secrets & Credentials Hygiene | ✅ PASS | Reuses Azure Speech creds via `config.py` (adds `AZURE_SPEECH_KEY`/`AZURE_SPEECH_REGION` fields sourced from Vault/Key Vault — no hardcoding). |
| V. AI Agent Safety & PII | ✅ PASS | Guardrails still run in `agents/interview/turn` **before** any TTS; blocked content is never synthesized or stored (FR-007). TTS only ever speaks post-guardrail agent text. |
| VI. Multi-Tenant Isolation | ✅ PASS | Session is RLS-scoped (company_id set on the WS connection); no new data paths. |
| VII. Observability & Reliability | ✅ PASS | Existing `audit_log` interview-turn events cover streamed turns; streaming failures emit a fallback event. `/health` unaffected. |
| VIII. Test Coverage (NON-NEGOTIABLE) | ✅ PASS (gating) | Streaming turn handling (end-of-speech finalize, chunked output ordering, guardrail-still-blocks, transcript parity, turn-based fallback) gets failing-first tests in the mandated voice-interview domain. |

**Performance gate**: SC-001 (p95 ≤ 2 s) is a **tracked target**, not a hard merge gate
(third-party speech-service variance) — measured by a streaming-latency check in `infra/perf/`.

**Post-Phase 1 re-check**: ✅ No new violations. The design adds a streaming branch + two speech
services and one column; it introduces no new agent bypass, no new secret source, no new tenant
path, and preserves the guardrail-before-response invariant.

## Project Structure

### Documentation (this feature)

```text
specs/017-video-interview/
├── plan.md              # This file
├── research.md          # Phase 0 — provider, VAD, async-bridge, protocol decisions
├── data-model.md        # Phase 1 — streaming_mode column + reused entities
├── quickstart.md        # Phase 1 — streaming-interview validation guide
├── contracts/
│   └── ws-streaming.md  # Phase 1 — WebSocket streaming sub-protocol (messages)
└── tasks.md             # Phase 2 — generated by /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── services/
│   │   ├── streaming_stt_service.py   # NEW — Azure push-stream recognizer, callbacks → asyncio.Queue
│   │   ├── streaming_tts_service.py   # NEW — Azure streaming synthesis, yields mp3 chunks
│   │   └── interview_service.py       # MODIFY — handle_streaming_turn reusing the turn-core
│   ├── api/routers/
│   │   └── interviews.py              # MODIFY — streaming branch in the WS loop (audio_frame / end_of_speech / ai_audio_chunk)
│   └── config.py                      # MODIFY — AZURE_SPEECH_KEY / AZURE_SPEECH_REGION (Vault/Key Vault)
├── pyproject.toml                     # MODIFY — + azure-cognitiveservices-speech
├── alembic/versions/                  # NEW — interview_sessions.streaming_mode column
└── tests/integration/
    └── test_interview_streaming.py    # NEW — TDD-gated streaming turn tests

frontend/
├── package.json                       # MODIFY — + onnxruntime-web
├── public/models/                     # NEW — bundled silero-vad ONNX model asset
└── src/
    ├── audio/
    │   ├── capture-worklet.ts         # NEW — AudioWorklet PCM capture processor
    │   └── vad.ts                     # NEW — silero-vad (onnxruntime-web) end-of-speech detection
    ├── services/interview-ws.ts       # MODIFY — streaming sub-protocol (frames, end_of_speech, audio chunks)
    └── pages/interview/InterviewRoomPage.tsx  # MODIFY — continuous capture, VAD, MediaSource playback, half-duplex
```

**Structure Decision**: Reuse the existing interview WebSocket and `InterviewService` turn-core
(history → agents/guardrails → persist → evaluation). Streaming changes only the **edges**: a
client-VAD-driven input stream and an Azure-streaming STT/TTS pair, behind the `streaming_mode`
flag, with the turn-based path as the default and the fallback.

## Complexity Tracking

No constitution violations requiring justification. The one area needing discipline — bridging the
synchronous Azure Speech SDK to asyncio without blocking the event loop — is addressed in
research.md Decision 4 and does not introduce a new architectural layer.
