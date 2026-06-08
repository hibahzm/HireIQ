# Tasks: Real-Time Streaming Voice Interview

**Input**: Design documents from `specs/017-video-interview/`

**Prerequisites**: [plan.md](plan.md) · [spec.md](spec.md) · [research.md](research.md) · [data-model.md](data-model.md) · [contracts/ws-streaming.md](contracts/ws-streaming.md) · [quickstart.md](quickstart.md)

**Tests**: Voice interview turn handling is a **Constitution Principle VIII TDD-mandated domain**, so
the streaming turn-handling tests below are written FIRST and confirmed failing before the
corresponding implementation. They are **gating** (no merge without them).

> Single user story (US1, P1): a natural, streaming voice conversation. Builds on the existing MVP
> interview WebSocket + `InterviewService` turn-core; streaming changes only the edges (client VAD +
> Azure streaming STT/TTS) behind a `streaming_mode` flag, with turn-based as the default and fallback.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no shared in-progress dependencies)
- **[Story]**: `US1` maps to User Story 1 in [spec.md](spec.md)
- Exact file paths are included in every description

---

## Phase 1: Setup

- [X] T001 [P] Add `azure-cognitiveservices-speech` to `backend/pyproject.toml` dependencies (streaming STT + TTS); rebuild the backend image / reinstall deps — closes the latent gap where the MVP TTS fallback imports it undeclared
- [X] T002 [P] Add `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION` settings to `backend/app/config.py` (defaults empty; wired into the Vault / Azure Key Vault loader like the other Azure secrets — no hardcoding, Constitution IV) — these are referenced by the existing `_azure_tts` but currently missing
- [X] T003 [P] Add `onnxruntime-web` to `frontend/package.json` dependencies and install (client-side VAD runtime)
- [X] T004 [P] Add the bundled silero-vad ONNX model asset under `frontend/public/models/` (served statically for onnxruntime-web)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Schema + session wiring both the streaming path and its fallback depend on.**

- [X] T005 Create an Alembic migration in `backend/alembic/versions/` adding `interview_sessions.streaming_mode BOOLEAN NOT NULL DEFAULT false` (additive; no backfill) per [data-model.md](data-model.md)
- [X] T006 Add `streaming_mode` to the `InterviewSession` model in `backend/app/models/interview_session.py`, add a job-level `streaming_interview` toggle (default off) set during job setup, and seed `streaming_mode` from that job toggle at session creation in the interview session repository/creation path (`backend/app/repositories/interview_repository.py`, in `InterviewSessionRepository.get_or_create_for_token`) — this is the concrete source for FR-005's per-job selection; both default off so existing jobs/sessions stay turn-based

---

## Phase 3: User Story 1 — Candidate Has a Natural, Streaming Conversation (Priority: P1) 🎯

**Goal**: A streaming-enabled interview where the candidate speaks continuously (no record/stop),
client-side VAD detects end-of-speech, the backend recognizes via Azure streaming STT, the existing
agent graph + guardrails produce the reply, and Azure streaming TTS sends audio chunks so playback
starts within ~2 s — with transcript parity and turn-based fallback.

**Independent Test**: On a `streaming_mode` session, speak without pressing any button → end-of-speech
is detected after a short silence, AI audio begins within ~2 s and before synthesis completes; harmful
input is blocked before any audio; the stored transcript matches a turn-based interview; disabling
streaming falls back to turn-based. See [quickstart.md](quickstart.md) Scenarios 1–6.

### Tests for User Story 1 (Constitution VIII — write FIRST, confirm FAILING before T010)

- [X] T007 [P] [US1] Write failing integration test: streaming turn handling in `backend/tests/integration/test_interview_streaming.py` — feed `audio_frame`s + `end_of_speech` (mock Azure STT to a finalized transcript, mock `agents/interview/turn`, mock Azure TTS to ordered chunks); assert the flow emits `ai_turn_text` then `ai_audio_chunk` messages in `seq` order followed by `ai_audio_end`, and that a candidate turn + AI turn are persisted to `interview_messages`
- [X] T008 [P] [US1] Write failing integration test: guardrails + parity + fallback in `backend/tests/integration/test_interview_streaming.py` — blocked input → `turn_blocked`, NO `ai_audio_chunk`, nothing stored (FR-007); a streamed turn writes `interview_messages` structurally identical to a turn-based turn (SC-003/FR-006); a forced streaming-init failure falls back to the turn-based path and the session still completes (FR-008)
- [X] T009 [P] [US1] Write failing frontend test: VAD + playback in `frontend/src/audio/vad.test.ts` (Vitest) — a sustained silence (≥ ~800 ms) finalizes the utterance while a short mid-sentence pause does NOT (SC-004); and a `MediaSource` SourceBuffer begins playback on the first `ai_audio_chunk` (SC-002)

### Implementation for User Story 1 — backend

- [X] T010 [US1] Create `StreamingSttService` in `backend/app/services/streaming_stt_service.py` — Azure `PushAudioInputStream` + continuous `SpeechRecognizer`; bridge `recognizing`/`recognized` callbacks to an `asyncio.Queue` via `loop.call_soon_threadsafe` (no event-loop blocking, Constitution II / research Decision 4); expose `push(frame)`, `next_partial()`, and an async `finalize()` resolved on `end_of_speech`
- [X] T011 [US1] Create `StreamingTtsService` in `backend/app/services/streaming_tts_service.py` — Azure streaming synthesis (16 kHz mono mp3) that yields audio chunks as they are produced (async generator backed by the synthesizing callback → `asyncio.Queue`); off-loop per research Decision 4
- [X] T012 [US1] Add `handle_streaming_turn` to `InterviewService` in `backend/app/services/interview_service.py` — take the finalized transcript, **assemble the buffered candidate PCM frames into a WAV and upload it via `StorageService`, setting `audio_blob_key` on the candidate `interview_messages` row** (parity with the turn-based `.webm` storage so SC-003/FR-006 hold), run the existing turn-core (append history → `agents/interview/turn` guardrails → persist candidate+AI `interview_messages` → Redis state → completion/evaluation trigger), and stream the guardrail-approved AI text through `StreamingTtsService`; never synthesize blocked content (FR-007)
- [X] T013 [US1] Add the streaming branch to the interview WS loop in `backend/app/api/routers/interviews.py` — include `streaming_mode` in `session_ready`; when true, handle `audio_frame`/`end_of_speech`, feed `StreamingSttService`, emit `partial_transcript`/`turn_processing`/`ai_turn_text`/`ai_audio_chunk`(seq)/`ai_audio_end` per [contracts/ws-streaming.md](contracts/ws-streaming.md); on any streaming failure fall back to the turn-based handler **and write an `audit_log` streaming-fallback event** (observability, Constitution VII); preserve the 24-hour resume path

### Implementation for User Story 1 — frontend

- [X] T014 [P] [US1] Create the AudioWorklet PCM capture processor in `frontend/src/audio/capture-worklet.ts` — continuous 16 kHz mono PCM frames posted to the main thread
- [X] T015 [P] [US1] Create client-side VAD in `frontend/src/audio/vad.ts` — silero-vad via onnxruntime-web over the captured frames; emit speech-start / end-of-speech after ≥ ~800 ms sustained silence (no false end on short pauses, SC-004)
- [X] T016 [US1] Extend the WS client in `frontend/src/services/interview-ws.ts` — send `audio_frame`/`end_of_speech`; handle `partial_transcript`/`ai_turn_text`/`ai_audio_chunk`/`ai_audio_end`; expose callbacks for transcript + audio-chunk consumption
- [X] T017 [US1] Update `InterviewRoomPage` in `frontend/src/pages/interview/InterviewRoomPage.tsx` — when `streaming_mode`, start continuous capture + VAD (no record/stop button), play `ai_audio_chunk`s via `MediaSource` (begin on first chunk), enforce half-duplex (suspend capture during AI playback, resume on `ai_audio_end`), and keep the text fallback; when not streaming, render the existing turn-based controls unchanged

**Checkpoint**: A `streaming_mode` interview is fully conversational end-to-end (SC-001/SC-002),
guardrails still block before audio (FR-007), the transcript matches turn-based (SC-003), and
disabling streaming or a failure falls back cleanly (FR-005/FR-008). Tests T007–T009 pass.

---

## Phase 4: Polish & Cross-Cutting

- [ ] T018 [P] Add a streaming-latency check to `infra/perf/` measuring `end_of_speech` → first `ai_audio_chunk`; report p95 and track against the ≤ 2 s target (SC-001 — tracked, not a hard gate). Record the STT-finalize→first-chunk and agent-call segments separately, since the agent/LLM turn dominates the budget
- [ ] T019 [P] Validate end-to-end per [quickstart.md](quickstart.md) Scenarios 1–6 (streaming conversation, no premature cut-off, transcript parity, guardrail block, fallback + resume, streaming-off default)

---

## Dependencies & Execution Order

- **Phase 1 (Setup)**: T001–T004 first (deps, config, model asset) — all `[P]`.
- **Phase 2 (Foundational)**: T005 (migration) then T006 (model + creation wiring) before US1.
- **Phase 3 (US1)**: Tests T007–T009 written and failing before implementation T010–T017.
  - Backend: T010 and T011 (`[P]`, different files) → T012 (service uses both) → T013 (WS wires it in).
  - Frontend: T014 → T015 → T016 → T017.
  - The backend chain (T010–T013) and frontend chain (T014–T017) run in parallel.
- **Phase 4 (Polish)**: After US1 implementation completes.

### Parallel Opportunities

- All of T001–T004 (setup) in parallel.
- T010 ∥ T011 (STT vs TTS service, different files).
- The entire frontend chain (T014–T017) in parallel with the backend chain (T010–T013).
- T007/T008/T009 (tests) authored together.

---

## Implementation Strategy

Single user story — deliver US1 end-to-end:

1. Phase 1: add the Azure Speech dep + config, onnxruntime-web + silero-vad asset.
2. Phase 2: `streaming_mode` migration + session wiring.
3. Write failing tests (T007–T009).
4. Backend streaming services + turn-core reuse + WS branch (T010–T013); frontend capture/VAD/playback
   (T014–T017) in parallel.
5. Polish: latency tracking (SC-001) and the quickstart scenarios.

---

## Notes

- Guardrails run in `agents/interview/turn` **before** any TTS — blocked content is never synthesized
  or stored (FR-007 / Constitution V).
- The Azure Speech SDK is callback/synchronous; it is bridged to asyncio via `asyncio.Queue` so the
  event loop is never blocked (Constitution II / research Decision 4).
- Turn-based remains the default and the fallback; existing (non-streaming) sessions are unchanged.
- Out of scope: barge-in (half-duplex in V2-3), non-English interviews, multi-party.
